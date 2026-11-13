"""Compare xopen in two virtualenvs (base and PR) on FASTQ data."""
import gzip
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys

ROUNDS = 7
RECORDS = 700_000  # about 220 MB of FASTQ


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


def table(title, base, pr, gz, raw):
    size = os.path.getsize(raw)
    print(f"\n### {title}: {size / 1e6:.0f} MB FASTQ, {os.path.getsize(gz) / 1e6:.0f} MB gzipped")
    cases = [
        ("read", "default", gz), ("read", "0", gz),
        ("lines", "default", gz), ("lines", "0", gz),
        ("write", "default", "out.gz"), ("write", "0", "out.gz"),
    ]
    print("| operation | threads | base MB/s | PR MB/s | speedup | base CPU s | PR CPU s | base out MB | PR out MB |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    mb = size / 1e6
    for op, threads, path in cases:
        res = {"base": ([], []), "pr": ([], [])}
        out_size = {}
        extra = (raw,) if op == "write" else ()
        for _ in range(ROUNDS):  # alternate base and PR
            for name, py in (("base", base), ("pr", pr)):
                w, c = run(py, op, path, threads, *extra)
                res[name][0].append(w)
                res[name][1].append(c)
                if op == "write":
                    out_size[name] = os.path.getsize(path) / 1e6
        bw, bc = (statistics.median(x) for x in res["base"])
        pw, pc = (statistics.median(x) for x in res["pr"])
        sizes = f"{out_size['base']:.1f} | {out_size['pr']:.1f}" if op == "write" else " | "
        print(f"| {op} | {threads} | {mb / bw:.0f} | {mb / pw:.0f} | {bw / pw:.2f}x | {bc:.2f} | {pc:.2f} | {sizes} |")


def main():
    base, pr = sys.argv[1], sys.argv[2]
    real = sys.argv[3] if len(sys.argv) > 3 else None
    print("machine:", platform.machine(), platform.platform())
    if sys.platform == "darwin":
        print("cpu:", subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                     capture_output=True, text=True).stdout.strip())
    else:
        print("cpu:", subprocess.run("lscpu | grep -E 'Model name|Vendor ID' | tr -s ' ' | tr '\n' ' '",
                                     shell=True, capture_output=True, text=True).stdout.strip())
    print("pigz:", shutil.which("pigz"), "| gzip:", shutil.which("gzip"))
    for name, py in (("base", base), ("pr", pr)):
        mods = subprocess.run(
            [py, "-c", "import xopen, sys; print(xopen.__version__, "
             "'isal' if xopen.igzip else 'no-isal', "
             "'zlib-ng' if xopen.gzip_ng else 'no-zlib-ng', sys.version.split()[0])"],
            capture_output=True, text=True, check=True).stdout.strip()
        print(f"{name}: {mods}")

    raw = "synthetic.fastq"
    make_fastq(raw)
    gz = "synthetic.fastq.gz"
    with open(raw, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, 1 << 20)
    table("synthetic FASTQ (gzip -6)", base, pr, gz, raw)

    if real and os.path.exists(real) and os.path.getsize(real) > 1_000_000:
        raw = "real.fastq"
        with gzip.open(real, "rb") as src, open(raw, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        table("real FASTQ " + os.path.basename(real) + " (as published)", base, pr, real, raw)
    else:
        print("\n(no real FASTQ available)")


main()
