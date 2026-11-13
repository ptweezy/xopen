"""Time each gzip backend that xopen can pick, in-process, on FASTQ-like data."""
import gzip
import os
import platform
import random
import shutil
import subprocess
import sys
import sysconfig
import time
import zlib

from isal import igzip, igzip_threaded, isal_zlib
from zlib_ng import gzip_ng, gzip_ng_threaded, zlib_ng

RECORDS = 700_000
REPS = 7


def make_fastq(path):
    rng = random.Random(0)
    acgt = bytes(b"ACGT"[i & 3] for i in range(256))
    qual = bytes(b"FFFFFFFFFFFF::,#"[i & 15] for i in range(256))
    with open(path, "wb") as f:
        for i in range(RECORDS):
            f.write(b"@read%d/1\n%s\n+\n%s\n" % (
                i, rng.randbytes(150).translate(acgt), rng.randbytes(150).translate(qual)))


def best(fn):
    times = []
    for _ in range(REPS):
        start = time.perf_counter()
        fn()
        times.append(time.perf_counter() - start)
    return min(times)


def read_all(opener):
    def run():
        with opener() as f:
            while f.read(128 * 1024):
                pass
    return run


def write_all(opener, data):
    def run():
        with opener() as f:
            view = memoryview(data)
            for i in range(0, len(view), 128 * 1024):
                f.write(view[i:i + 128 * 1024])
    return run


print("machine:", platform.machine(), platform.platform(), "| python", sys.version.split()[0])
if sys.platform == "darwin":
    print("cpu:", subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True).stdout.strip())
    print(subprocess.run("otool -L $(python -c 'import zlib; print(zlib.__file__)') | grep -i libz",
                         shell=True, capture_output=True, text=True).stdout.strip())
else:
    print("cpu:", subprocess.run("lscpu | grep -E 'Model name|Vendor ID' | tr -s ' '",
                                 shell=True, capture_output=True, text=True).stdout.strip())
    print(subprocess.run("ldd $(python -c 'import zlib; print(zlib.__file__)') | grep -i libz",
                         shell=True, capture_output=True, text=True).stdout.strip())
print("stdlib zlib runtime:", zlib.ZLIB_RUNTIME_VERSION, "| isal", isal_zlib.ISAL_VERSION if hasattr(isal_zlib, "ISAL_VERSION") else "?",
      "| zlib-ng", zlib_ng.ZLIBNG_VERSION if hasattr(zlib_ng, "ZLIBNG_VERSION") else "?")

raw = "data.fastq"
make_fastq(raw)
data = open(raw, "rb").read()
gz = "data.fastq.gz"
with open(gz, "wb") as dst:
    dst.write(gzip.compress(data, compresslevel=6))
mb = len(data) / 1e6
print(f"data: {mb:.0f} MB FASTQ, {os.path.getsize(gz) / 1e6:.0f} MB as gzip -6")

print("| backend | read MB/s |")
print("|---|---:|")
readers = [
    ("stdlib gzip", lambda: gzip.open(gz, "rb")),
    ("isal igzip", lambda: igzip.open(gz, "rb")),
    ("isal igzip_threaded (threads=1)", lambda: igzip_threaded.open(gz, "rb", threads=1)),
    ("zlib-ng gzip_ng", lambda: gzip_ng.open(gz, "rb")),
    ("zlib-ng gzip_ng_threaded (threads=1)", lambda: gzip_ng_threaded.open(gz, "rb", threads=1)),
]
for name, opener in readers:
    print(f"| {name} | {mb / best(read_all(opener)):.0f} |")

print("| backend | write MB/s | output MB |")
print("|---|---:|---:|")
writers = [
    ("stdlib gzip level 1", lambda: gzip.open("out.gz", "wb", compresslevel=1)),
    ("isal igzip level 1", lambda: igzip.open("out.gz", "wb", compresslevel=1)),
    ("isal igzip_threaded level 1 (threads=1)", lambda: igzip_threaded.open("out.gz", "wb", compresslevel=1, threads=1)),
    ("zlib-ng gzip_ng level 2", lambda: gzip_ng.open("out.gz", "wb", compresslevel=2)),
    ("zlib-ng gzip_ng_threaded level 2 (threads=1)", lambda: gzip_ng_threaded.open("out.gz", "wb", compresslevel=2, threads=1)),
]
for name, opener in writers:
    t = best(write_all(opener, data))
    print(f"| {name} | {mb / t:.0f} | {os.path.getsize('out.gz') / 1e6:.1f} |")
