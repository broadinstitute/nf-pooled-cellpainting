FROM python:3.11-slim

# Deps for bin/align_intraarm.py, bin/align_combined.py (and eventually bin/crop.py,
# which currently shares this image too): numpy/scipy/scikit-image for
# phase_cross_correlation + ndimage.shift, Pillow for TIFF I/O.
# procps provides `ps`, which Nextflow's own task-metrics trace shells out to
# inside the container - without it every process fails immediately with
# "Command 'ps' required by nextflow to collect task metrics cannot be found".
RUN apt-get update && apt-get install -y --no-install-recommends \
        procps \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        numpy \
        scipy \
        scikit-image \
        pillow \
        tifffile

# Nextflow runs this container as a non-root, HOME-less user, so matplotlib
# (pulled in transitively by scikit-image) can't write its default config dir
# under / and prints a permission-denied warning to stderr on every invocation.
ENV MPLCONFIGDIR=/tmp/matplotlib
