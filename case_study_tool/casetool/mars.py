"""MARS retrieval with on-disk caching and parallel worker processes."""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import multiprocessing as mp
import os
from dataclasses import dataclass
from pathlib import Path

from casetool.config import CaseConfig
from casetool.models import ModelSpec


@dataclass(frozen=True)
class Job:
    """One MARS retrieval: a model/run/variable combination."""

    model_key: str
    label: str
    lead: int | None  # None for the orography job
    variable: str  # tp | ws10 | orog
    requests: tuple[dict, ...]  # one per candidate expver, tried in order
    caches: tuple[str, ...]


def _cache_name(request: dict) -> str:
    digest = hashlib.sha1(repr(sorted(request.items())).encode()).hexdigest()[:12]
    return (
        f"{request['class']}_{request['expver']}_{request['date']}{request['time']}_"
        f"{digest}.grib"
    )


def _request(model: ModelSpec, expver: str, base, param: str, steps, area) -> dict:
    req = {
        "class": model.mars_class,
        "stream": model.stream,
        "type": model.mars_type,
        "expver": expver,
        "levtype": "sfc",
        "param": param,
        "date": base.strftime("%Y%m%d"),
        "time": base.strftime("%H%M"),
        "step": "/".join(str(s) for s in steps),
        "area": [float(v) for v in area],
        "expect": "any",
    }
    req.update(model.extra)
    return req


def build_jobs(cfg: CaseConfig, valid: set[tuple[str, int]]) -> list[Job]:
    """Return retrieval jobs for every valid (model, lead) plus orography per model."""
    area = cfg.area()
    cache_dir = cfg.cache_dir / "mars"
    jobs = []
    for model in cfg.models:
        for lead in cfg.leads:
            if (model.key, lead) not in valid:
                continue
            base = cfg.base_time(lead)
            steps = cfg.steps(model, lead)
            reqs = tuple(
                _request(model, ev, base, model.param(cfg.variable), steps, area)
                for ev in model.expvers
            )
            jobs.append(
                Job(
                    model.key,
                    model.label,
                    lead,
                    cfg.variable,
                    reqs,
                    tuple(str(cache_dir / _cache_name(r)) for r in reqs),
                )
            )
        if cfg.plot.orography:
            leads = [ld for ld in cfg.leads if (model.key, ld) in valid]
            if leads:
                base = cfg.base_time(leads[0])
                reqs = tuple(
                    _request(model, ev, base, model.param("orog"), [0], area)
                    for ev in model.expvers
                )
                jobs.append(
                    Job(
                        model.key,
                        model.label,
                        None,
                        "orog",
                        reqs,
                        tuple(str(cache_dir / _cache_name(r)) for r in reqs),
                    )
                )
    return jobs


def _fetch(job: Job, force: bool) -> tuple[Job, str | None, str | None, str]:
    """Worker: try each candidate expver; return (job, path, expver, message)."""
    import earthkit.data as ekd  # noqa: PLC0415

    tmp = f"/tmp/mars_tmp_{os.environ.get('USER', 'casetool')}"
    os.makedirs(tmp, exist_ok=True)
    os.environ["TMPDIR"] = tmp
    if not force:
        # A fallback expver cached on an earlier run is reused without retrying the first.
        for request, cache in zip(job.requests, job.caches, strict=True):
            if Path(cache).exists():
                return job, cache, request["expver"], "cached"
    messages = []
    for request, cache in zip(job.requests, job.caches, strict=True):
        path = Path(cache)
        try:
            src = ekd.from_source("mars", **request)
            ds = src.to_fieldlist() if hasattr(src, "to_fieldlist") else src
            if len(ds) == 0:
                messages.append(f"{request['expver']}: no fields")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".part")
            if hasattr(ds, "to_target"):
                ds.to_target("file", str(tmp_path))
            else:
                ds.save(str(tmp_path))
            tmp_path.replace(path)
            return job, cache, request["expver"], f"retrieved {len(ds)} fields"
        except Exception as exc:  # noqa: BLE001
            messages.append(f"{request['expver']}: {exc}".splitlines()[0][:200])
    return job, None, None, "; ".join(messages) or "failed"


def _log_to(path: str) -> None:
    """Worker initialiser: send the MARS client's console output to ``path``."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)


def fetch_all(jobs: list[Job], workers: int = 6, force: bool = False) -> dict:
    """Run all jobs in parallel processes; return {(model_key, lead|'orog'): result}."""
    results = {}
    pending = [j for j in jobs if force or not any(Path(c).exists() for c in j.caches)]
    for job in jobs:
        if job not in pending:
            results[_key(job)] = _fetch(job, False)
    if pending:
        log = str(Path(pending[0].caches[0]).parent / "mars.log")
        print(
            f"Retrieving {len(pending)} field set(s) from MARS with {workers} worker(s) "
            f"(MARS log: {log})..."
        )
        ctx = mp.get_context("spawn")
        with cf.ProcessPoolExecutor(
            max_workers=workers, mp_context=ctx, initializer=_log_to, initargs=(log,)
        ) as pool:
            futures = [pool.submit(_fetch, job, force) for job in pending]
            for fut in cf.as_completed(futures):
                job, path, expver, msg = fut.result()
                results[_key(job)] = (job, path, expver, msg)
                what = "orography" if job.lead is None else f"T+{job.lead}h"
                ok = "\u2713" if path else "\u2717"
                print(f"  {ok} {job.label} {what}: {msg}", flush=True)
    return results


def _key(job: Job):
    return (job.model_key, "orog" if job.lead is None else job.lead)
