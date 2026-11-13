"""Compare two virtualenvs (xopen without and with python-isal) on FASTQ-like data."""
import gzip
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys

ROUNDS = 7
RECORDS = 700_000  # about 230 MB of FASTQ


def make_fastq(path):
    rng = random.Random(0)
    acgt = bytes(b"ACGT"[i & 3] for i in range(256))
    # Binned qualities, mostly high, as on recent Illumina instruments.
    qual = bytes(b"FFFFFFFFFFFF::,#"[i & 15] for i in range(256))
    with open(path, "wb") as f:
        for i in range(RECORDS):
            seq = rng.randbytes(150).translate(acgt)
            q = rng.randbytes(150).translate(qual)
            f.write(b"@read%d/1\n%s\n+\n%s\n" % (i, seq, q))


def run(python, op, path, threads, *extra):
    out = subprocess.run(
        [python, "bench/worker.py", op, path, threads, *extra],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    return float(out[0]), float(out[1])


def main():
    base, pr = sys.argv[1], sys.argv[2]
    print("machine:", platform.machine(), platform.platform())
    print("cpu:", subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True).stdout.strip())
    print("pigz:", shutil.which("pigz"), "| gzip:", shutil.which("gzip"))
    for name, py in (("base", base), ("pr", pr)):
        mods = subprocess.run(
            [py, "-c", "import xopen, sys; print(xopen.__version__, "
             "'isal' if xopen.igzip else 'no-isal', "
             "'zlib-ng' if xopen.gzip_ng else 'no-zlib-ng', sys.version.split()[0])"],
            capture_output=True, text=True, check=True).stdout.strip()
        print(f"{name}: {mods}")

    raw = "data.fastq"
    make_fastq(raw)
    size = os.path.getsize(raw)
    gz = "data.fastq.gz"
    with open(raw, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    print(f"data: {size / 1e6:.0f} MB FASTQ, {os.path.getsize(gz) / 1e6:.0f} MB as gzip -6")

    cases = [
        ("read", "default", gz), ("read", "0", gz),
        ("lines", "default", gz), ("lines", "0", gz),
        ("write", "default", "out.gz"), ("write", "0", "out.gz"),
    ]
    print("| operation | threads | base wall s | PR wall s | speedup | base CPU s | PR CPU s | base size MB | PR size MB |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for op, threads, path in cases:
        res = {}
        for name, py in (("base", base), ("pr", pr)):
            walls, cpus = [], []
            extra = (raw,) if op == "write" else ()
            for _ in range(ROUNDS):
                w, c = run(py, op, path, threads, *extra)
                walls.append(w)
                cpus.append(c)
            out_size = os.path.getsize(path) / 1e6 if op == "write" else float("nan")
            res[name] = (statistics.median(walls), statistics.median(cpus), out_size)
        b, p = res["base"], res["pr"]
        sizes = f"{b[2]:.1f} | {p[2]:.1f}" if op == "write" else "| "
        print(f"| {op} | {threads} | {b[0]:.2f} | {p[0]:.2f} | {b[0] / p[0]:.2f}x | {b[1]:.2f} | {p[1]:.2f} | {sizes} |")


main()
