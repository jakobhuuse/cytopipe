
export JOBNAME=parsl.htex_default_for_cytotable.block-0.1781608201.3884642
set -e
export CORES=$(getconf _NPROCESSORS_ONLN)
[[ "1" == "1" ]] && echo "Found cores : $CORES"
WORKERCOUNT=1
FAILONANY=0
PIDS=""

CMD() {
process_worker_pool.py   -a 127.0.0.1,78.91.96.174,10.218.118.107 -p 0 -c 1.0 -m None --poll 10 --port=54182 --cert_dir /Users/jakob/Documents/SINTEF/project/cytopipe/runinfo/001/htex_default_for_cytotable/certificates --logdir=/Users/jakob/Documents/SINTEF/project/cytopipe/runinfo/001/htex_default_for_cytotable --logconf=None --block_id=0 --hb_period=30  --hb_threshold=120 --drain_period=None --cpu-affinity none  --mpi-launcher=mpiexec --available-accelerators 
}
for COUNT in $(seq 1 1 $WORKERCOUNT); do
    [[ "1" == "1" ]] && echo "Launching worker: $COUNT"
    CMD $COUNT &
    PIDS="$PIDS $!"
done

ALLFAILED=1
ANYFAILED=0
for PID in $PIDS ; do
    wait $PID
    if [ "$?" != "0" ]; then
        ANYFAILED=1
    else
        ALLFAILED=0
    fi
done

[[ "1" == "1" ]] && echo "All workers done"
if [ "$FAILONANY" == "1" ]; then
    exit $ANYFAILED
else
    exit $ALLFAILED
fi
