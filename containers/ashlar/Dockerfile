FROM python:3.11-slim

# ashlar's package imports a bioformats reader backend (pyjnius, needs a JVM) even
# when only its plain fileseries reader is used at runtime (as bin/stitch.py does).
# Without a JDK, `ashlar` dies on startup with "Exception: Unable to find javac"
# (confirmed in production on Seqera, running the stitch_align_crop_v1 image).
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

# In Seqera's cloud execution environment, the JVM's hsperfdata shared-memory file
# can fail to write, printing "[0.005s][warning][perf,memops] Cannot use the file
# ..." to STDOUT - which also corrupts versions.yml capture of `ashlar --version`.
# Disabling JVM perf data avoids the warning entirely.
ENV JAVA_TOOL_OPTIONS=-XX:-UsePerfData
