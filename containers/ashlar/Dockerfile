FROM python:3.11-slim

# ashlar's package imports a bioformats reader backend (pyjnius, needs a JVM) even
# when only its plain fileseries reader is used at runtime (as bin/stitch.py does).
# NOTE: unverified in this environment (no internet/build access here) - if
# `ashlar --version` or `pip install ashlar` fails without a JDK present, this is
# the first thing to check; if ashlar imports fine without it, this can be dropped.
# procps provides `ps`, which Nextflow's own task-metrics trace shells out to
# inside the container - without it every process fails immediately with
# "Command 'ps' required by nextflow to collect task metrics cannot be found".
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jdk-headless \
        procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        numpy \
        pillow \
        tifffile \
        ashlar

# Nextflow runs this container as a non-root, HOME-less user, so matplotlib
# (pulled in transitively by ashlar) can't write its default config dir under
# / and prints a permission-denied warning to stderr on every invocation -
# including `ashlar --version`, where it can corrupt versions.yml capture.
ENV MPLCONFIGDIR=/tmp/matplotlib
