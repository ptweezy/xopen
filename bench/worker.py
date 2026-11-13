"""Run one xopen operation in a fresh process and print wall and CPU seconds."""
import resource
import sys
import time

from xopen import xopen

op, path, threads = sys.argv[1], sys.argv[2], sys.argv[3]
threads = None if threads == "default" else int(threads)

start = time.perf_counter()
if op == "read":
    n = 0
    with xopen(path, "rb", threads=threads) as f:
        while chunk := f.read(128 * 1024):
            n += len(chunk)
elif op == "lines":
    n = 0
    with xopen(path, "rb", threads=threads) as f:
        for line in f:
            n += len(line)
elif op == "write":
    data = open(sys.argv[4], "rb").read()
    start = time.perf_counter()
    with xopen(path, "wb", threads=threads) as f:
        view = memoryview(data)
        for i in range(0, len(view), 128 * 1024):
            f.write(view[i : i + 128 * 1024])
    n = len(data)
wall = time.perf_counter() - start
me = resource.getrusage(resource.RUSAGE_SELF)
kids = resource.getrusage(resource.RUSAGE_CHILDREN)
cpu = me.ru_utime + me.ru_stime + kids.ru_utime + kids.ru_stime
print(f"{wall:.4f} {cpu:.4f} {n}")
