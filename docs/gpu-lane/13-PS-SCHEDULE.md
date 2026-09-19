# The numbers on the problem statement's own schedule

The statement specifies the grid it wants: "resolution is high (e.g., 5cm
cells) within a 10m radius and decreases (e.g., 50cm cells) up to a 100m
radius". That is `configs/schedule_5_10_50.yaml`, `--schedule 5/10/50`:

    ring 0   to  10 m at  5 cm   160,000 cells
    ring 1   to  25 m at 10 cm   210,000 cells
    ring 2   to 100 m at 50 cm   150,000 cells
                                 520,000 cells, 6.24 MB at 12 B/cell

Every figure this project has published is on the DEFAULT 5/10/20/40 schedule
(745,000 cells, 8.94 MB), which tops out at 40 cm rather than 50. Both are
honest; only one of them is the one the statement asked for, and a reader
checking the brief against the report will look for 5 and 50.

## Latency, seq 08, 200 frames, CUDA

    stage             p50      p99      max   share   x10Hz
    ground          12.70    15.82    16.40     58%     6.3x
    shift            2.44     4.33     4.89     11%    23.1x
    scatter          1.51     2.18     2.77      7%    45.8x
    cleanup          1.42     2.43     2.45      6%    41.2x
    range_image      1.19     3.30     3.81      5%    30.3x
    FRAME           21.94    28.40    29.84    100%     3.5x

    45.6 FPS p50, 35.2 FPS p99 -- MEETS 10 Hz at p99, 3.5x headroom
    free-running: p50 21.57, p99 28.77 -> 46.4 / 34.8 FPS

Within noise of the 4-ring schedule's 22.3 / 26.7 ms. Dropping ring 3 and
coarsening ring 2 to 50 cm removes 225,000 cells and does not move the frame
time, because the frame is dominated by ground segmentation (58% of p50,
Patchwork++ on the host) rather than by cell count.

## Memory

    Dense 3D voxels, 5 cm, 200x200x8 m, 1 B/voxel      2.56 GB
    Uniform 5 cm 2.5D, same 12 B cell                  192.00 MB
    Ours, 5/10/50                                        6.24 MB

    30.8x smaller than the uniform 2.5D grid
    410x smaller than the dense 3D baseline

Both are pure cell-count ratios and are invariant to bytes per cell.

## Classification accuracy, binned to THESE rings

    bin      range m     returns      scored   acc19    mIoU  3-group  drivable
    ring 0      0-10  11,671,697  11,348,345   93.2%   65.4%    95.1%     67.6%
    ring 1     10-25   8,572,694   8,330,568   88.2%   67.0%    91.8%     60.5%
    ring 2    25-100   4,296,713   3,062,980   85.4%   55.9%    92.0%     51.2%
    pooled     0-inf  24,541,104  22,741,893   90.3%

⚑ RING 2 IS ONLY SCORED OVER ITS INNER HALF. It spans 25-100 m and holds
  4,296,713 returns, of which 3,062,980 carry a ground-truth label -- every
  labelled one is inside 50 m, because SemanticKITTI stops labelling there.
  The row is a 25-50 m number wearing a 25-100 m label. Say so wherever it is
  quoted, or quote the 10,25,50,100 binning instead, where the unscorable
  range is its own row and is marked NOT SCORABLE.

  This is a property of the dataset, not of the map: the map builds ring 2 out
  to 100 m and its GEOMETRIC accuracy there is measured elsewhere. It is the
  CLASSIFICATION accuracy beyond 50 m that no dataset here can support.

## Reproducing

    python scripts/timing_table.py --seq 08 --frames 200 --device cuda --schedule 5/10/50
    python scripts/memory_table.py --schedule 5/10/50
    python scripts/accuracy_by_range.py --seq 08 --frames 200 --edges 10,25,100 --fast-scatter
