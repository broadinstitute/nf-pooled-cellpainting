FROM python:3.11-slim

# Deps for bin/align_intraarm.py, bin/align_combined.py (and eventually bin/crop.py,
# which currently shares this image too): numpy/scipy/scikit-image for
# phase_cross_correlation + ndimage.shift, Pillow for TIFF I/O.
# procps provides `ps`, which Nextflow's own task-metrics trace shells out to
# inside the container - without it every process fails immediately with
# "Command 'ps' required by nextflow to collect task metrics cannot be found".
#
# ashlar imports a bioformats reader backend (pyjnius, needs a JVM) at module load
# time even when only its plain fileseries reader is used at runtime (as
# bin/stitch.py does) - without a JDK, `ashlar` dies on startup with
# "Exception: Unable to find javac" (confirmed in production on Seqera).
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-jdk-headless \
        procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        numpy \
        scipy \
        scikit-image \
        pillow \
        tifffile \
        ashlar

# Nextflow runs this container as a non-root, HOME-less user, so matplotlib
# (pulled in transitively by scikit-image) can't write its default config dir
# under / and prints a permission-denied warning to stderr on every invocation.
ENV MPLCONFIGDIR=/tmp/matplotlib

# In Seqera's cloud execution environment, the JVM's hsperfdata shared-memory file
# can fail to write, printing "[0.005s][warning][perf,memops] Cannot use the file
# ..." to STDOUT (seen in production there, not reproducible locally). modules/
# local/stitch/main.nf captures `ashlar --version` output into versions.yml, so
# that warning line (starting with `[`) breaks YAML parsing of the whole file.
# Disabling JVM perf data avoids the warning entirely - verified locally that
# `-XX:-UsePerfData` is picked up (STDERR-only notice) and leaves STDOUT clean.
ENV JAVA_TOOL_OPTIONS=-XX:-UsePerfData
