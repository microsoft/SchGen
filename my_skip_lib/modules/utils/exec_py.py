import os, io, sys, tempfile, traceback, subprocess, signal
from pathlib import Path

def exec_generated_lines(
    lines,
    project_path: str | Path | None = None,
    working_dir: str | Path | None = None,
    keep_file: bool = False,
    filename_hint: str = "generated_exec.py",
    timeout: float | None = None,   
):
    code = "\n".join(str(x) for x in lines if x is not None)

    if keep_file:
        tmpdir = Path(tempfile.mkdtemp(prefix="gen_exec_"))
        cleanup_dir = False
    else:
        _td = tempfile.TemporaryDirectory(prefix="gen_exec_")
        tmpdir = Path(_td.name)
        cleanup_dir = True

    tmp_path = tmpdir / filename_hint
    tmp_path.write_text(code, encoding="utf-8")

    env = os.environ.copy()
    if project_path is not None:
        env["PROJECT_PATH"] = str(Path(project_path).resolve())
    env.setdefault("PYTHONUNBUFFERED", "1")

    cwd = str(Path(working_dir).resolve()) if working_dir else None

    if os.name == "nt":
        creation = subprocess.CREATE_NEW_PROCESS_GROUP
        popen_session_kwargs = {"creationflags": creation}
    else:
        popen_session_kwargs = {"start_new_session": True}

    cmd = [sys.executable, "-u", str(tmp_path)]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
            **popen_session_kwargs,
        )
        try:
            out_text, err_text = proc.communicate(timeout=timeout)
            rc = proc.returncode
            success = (rc == 0)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                proc.kill()
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
            out_text, err_text = proc.communicate()
            success = False
            err_text = (err_text or "") + f"\n[Timeout] exceeded {timeout}s"
    except Exception:
        success = False
        out_text, err_text = "", traceback.format_exc()
    finally:
        if cleanup_dir:
            try:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
                tmp_file_report = None
            except Exception:
                tmp_file_report = str(tmp_path)
        else:
            tmp_file_report = str(tmp_path)

    combined = out_text + ("\n" if out_text and err_text else "") + (err_text or "")
    errors = sum(1 for ln in combined.splitlines() if "error" in ln.lower())

    return {
        "success": success,
        "tmp_file": tmp_file_report,
        "stdout": out_text or "",
        "stderr": err_text or "",
        "combined": combined,
        "errors": errors,
        "traceback": None if success else (err_text or ""),
    }