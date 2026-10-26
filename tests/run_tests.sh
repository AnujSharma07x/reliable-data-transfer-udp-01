#!/usr/bin/env bash
# run_tests.sh - end-to-end SAW + GBN + SR tests over localhost.
# Each test: start server, run client, then require: both exit 0, a RESULT
# line, identical file (cmp + sha256), and optional exact RESULT values.
cd "$(dirname "$0")/.." || exit 1
mkdir -p tests/tmp
T=tests/tmp
PORT=${BASE_PORT:-9200}
PASS=0; FAIL=0

# Same inputs every run (generated from a fixed seed, not /dev/urandom)
python3 -c "import random; random.seed(1234); open('$T/big.bin','wb').write(random.randbytes(1048576))"
python3 -c "import random; random.seed(99);   open('$T/small.bin','wb').write(random.randbytes(20000))"
python3 -c "import random; random.seed(77);   open('$T/mid.bin','wb').write(random.randbytes(200000))"
python3 -c "
import random; r = random.Random(5)
for n in (0, 1, 1024, 2048, 3000): open('$T/f%d.bin' % n, 'wb').write(r.randbytes(n))"

# run <name> <proto> <file> "<server opts>" "<client opts>" [expect_retx] ["key=val ..."]
#   expect_retx = yes : retransmissions must be > 0
#   key=val ...       : these RESULT fields must match exactly
run() {
    local name=$1 proto=$2 file=$3 sopts=$4 copts=$5 expect_retx=${6:-no} exact=${7:-}
    PORT=$((PORT + 1))
    local out=$T/out_$PORT.bin slog=$T/server_$PORT.log clog=$T/client_$PORT.log

    timeout 120 ./server "$PORT" "$file" --proto "$proto" $sopts >"$slog" 2>&1 &
    local spid=$!
    sleep 0.2
    timeout 120 ./client 127.0.0.1 "$PORT" "$out" --proto "$proto" $copts >"$clog" 2>&1
    local crc=$?
    wait "$spid"
    local src=$?

    local result retx ok=1 why=""
    [ $src -eq 0 ] || { ok=0; why="server exit $src"; }
    [ $crc -eq 0 ] || { ok=0; why="$why client exit $crc"; }
    result=$(grep '^RESULT' "$slog")
    retx=$(echo "$result" | sed -n 's/.*retransmissions=\([0-9]*\).*/\1/p')
    cmp -s "$file" "$out" || ok=0
    [ "$(sha256sum <"$file")" = "$(sha256sum <"$out")" ] || ok=0
    [ -n "$result" ] || ok=0
    if [ "$expect_retx" = yes ] && [ "${retx:-0}" -eq 0 ]; then ok=0; why="$why no retx"; fi
    local kv
    for kv in $exact; do
        echo " ${result#RESULT } " | grep -q " $kv " || { ok=0; why="$why want $kv"; }
    done

    if [ $ok -eq 1 ]; then
        PASS=$((PASS + 1)); printf "PASS  %-38s %s\n" "$name" "${result#RESULT }"
        printf "      %s\n" "$(grep '^RECV' "$clog")"
    else
        FAIL=$((FAIL + 1)); printf "FAIL  %-38s %s (logs: %s %s)\n" "$name" "$why" "$slog" "$clog"
    fi
}

echo "== Stop-and-Wait end-to-end tests =="
run "1 normal transfer (1 MB)"            saw $T/big.bin   ""                   ""
run "2 lost DATA (drop every 10th)"      saw $T/big.bin   "--drop-every 10"    ""                yes
run "3 corrupted DATA (every 7th)"       saw $T/big.bin   "--corrupt-every 7"  ""                yes
run "4 lost ACK (drop every 8th)"        saw $T/big.bin   ""                   "--drop-every 8"  yes
run "5 corrupted ACK (every 9th)"        saw $T/big.bin   ""                   "--corrupt-every 9" yes
run "6 delayed ACK 20ms, adaptive RTO"   saw $T/small.bin ""                   "--delay-ms 20"
run "7 delayed ACK 25ms, fixed RTO 100"  saw $T/small.bin "--rto 100"          "--delay-ms 25"
# --delay-ms is now the emulator's non-blocking delay (alias of --delay).
run "8 combined loss+corruption"         saw $T/big.bin   "--drop-every 11 --corrupt-every 13" "--drop-every 17" yes

echo
echo "== Go-Back-N end-to-end tests =="
for w in 1 4 8 16 32; do
run "W$w normal, window $w"                gbn $T/big.bin "--window $w" "--window $w"
done
run "G6 lost DATA, window 8"             gbn $T/big.bin "--window 8 --drop-every 10"    "--window 8"   yes
run "G7 lost DATA, window 32"            gbn $T/big.bin "--window 32 --drop-every 10"   "--window 32"  yes
run "G8 corrupted DATA, window 8"        gbn $T/big.bin "--window 8 --corrupt-every 7"  "--window 8"   yes
run "G9 lost ACK, window 8"              gbn $T/big.bin "--window 8"  "--window 8 --drop-every 8"
run "G10 corrupted ACK, window 8"        gbn $T/big.bin "--window 8"  "--window 8 --corrupt-every 9"
run "G11 delayed ACK 20ms, window 8"     gbn $T/small.bin "--window 8" "--window 8 --delay-ms 20"
run "G12 combined, window 16"            gbn $T/big.bin "--window 16 --drop-every 11 --corrupt-every 13" "--window 16 --drop-every 17" yes

echo
echo "== Exact-behaviour tests (review T1-T8) =="
# small.bin = 21 packets (seq 0..19 data, 20 EOF). Send #15 = seq 14 is lost once;
# a timeout must resend exactly [base, next): 1 / 4 / 7 packets for w = 1 / 4 / 8.
run "T1a single loss, gbn w1 -> retx 1"   gbn $T/small.bin "--window 1 --drop-every 15" "--window 1" no "packets_sent=22 retransmissions=1 timeouts=1"
run "T1b single loss, gbn w4 -> retx 4"   gbn $T/small.bin "--window 4 --drop-every 15" "--window 4" no "packets_sent=25 retransmissions=4 timeouts=1"
run "T1c single loss, gbn w8 -> retx 7"   gbn $T/small.bin "--window 8 --drop-every 15" "--window 8" no "packets_sent=28 retransmissions=7 timeouts=1"
run "T1d single loss, saw -> retx 1"      saw $T/small.bin "--drop-every 15" "" no "packets_sent=22 retransmissions=1 timeouts=1"
# f3000 = seq 0..2 data + seq 3 EOF; 4th send = EOF.
run "T2a EOF lost, gbn w8"                gbn $T/f3000.bin "--window 8 --drop-every 4" "--window 8" no "packets_sent=5 retransmissions=1 timeouts=1"
run "T2b EOF lost, saw"                   saw $T/f3000.bin "--drop-every 4" "" no "packets_sent=5 retransmissions=1 timeouts=1"
# client sends HELLO, ACK0, ACK1, ACK2, ACK3(EOF): 5th = final ACK.
run "T3a final ACK lost, gbn, rto 1500"   gbn $T/f3000.bin "--window 8 --rto 1500" "--window 8 --drop-every 5" no "retransmissions=1 timeouts=1"
run "T3b final ACK lost, saw, rto 1500"   saw $T/f3000.bin "--rto 1500" "--drop-every 5" no "retransmissions=1 timeouts=1"
run "T3c final ACK lost, gbn, adaptive"   gbn $T/f3000.bin "--window 8" "--window 8 --drop-every 5" no "retransmissions=1 timeouts=1"
run "T4a no spurious retx, saw 20ms"      saw $T/small.bin "" "--delay-ms 20" no "retransmissions=0"
run "T4b no spurious retx, saw 30ms"      saw $T/small.bin "" "--delay-ms 30" no "retransmissions=0"
for n in 0 1 1024 2048; do
  pk=$(( (n + 1023) / 1024 + 1 ))   # ceil(n/1024) data packets + 1 EOF
  run "T5 size $n B, saw -> $pk pkts"     saw $T/f$n.bin "" "" no "packets_sent=$pk retransmissions=0"
  run "T5 size $n B, gbn w4 -> $pk pkts"  gbn $T/f$n.bin "--window 4" "--window 4" no "packets_sent=$pk retransmissions=0"
done
run "T6a window 2"                        gbn $T/small.bin "--window 2" "--window 2" no "packets_sent=21 retransmissions=0"
run "T6b window 32 > 4 packets"           gbn $T/f3000.bin "--window 32" "--window 32" no "packets_sent=4 retransmissions=0"
run "T8 lost ACK costs GBN nothing"       gbn $T/big.bin "--window 8" "--window 8 --drop-every 8" no "retransmissions=0"

echo
echo "== Selective Repeat end-to-end tests =="
for w in 1 2 4 8 16 32; do
run "SW$w normal, window $w"              sr $T/big.bin "--window $w" "--window $w" no "packets_sent=1025 retransmissions=0"
done
run "SR1 lost DATA, window 8"            sr $T/big.bin "--window 8 --drop-every 10"   "--window 8"  yes
run "SR2 lost DATA, window 32"           sr $T/big.bin "--window 32 --drop-every 10"  "--window 32" yes
run "SR3 corrupted DATA, window 8"       sr $T/big.bin "--window 8 --corrupt-every 7" "--window 8"  yes
run "SR4 lost ACK, window 8"             sr $T/big.bin "--window 8"  "--window 8 --drop-every 8"  yes
run "SR5 corrupted ACK, window 8"        sr $T/big.bin "--window 8"  "--window 8 --corrupt-every 9" yes
# The old placeholder delay was a BLOCKING sleep that serialised ACKs and caused
# spurious SR retransmissions at w8. The emulator's delay is non-blocking, so
# every ACK is delayed equally and both windows must be spurious-free.
run "SR6a delayed ACK 20ms, window 2"    sr $T/small.bin "--window 2" "--window 2 --delay-ms 20" no "retransmissions=0"
run "SR6b delayed ACK 20ms, window 8"    sr $T/small.bin "--window 8" "--window 8 --delay-ms 20" no "retransmissions=0"
run "SR7 combined, window 16"            sr $T/big.bin "--window 16 --drop-every 11 --corrupt-every 13" "--window 16 --drop-every 17" yes
# One loss: SR resends ONLY the lost packet, whatever the window (GBN: 1/4/7).
run "SR8a single loss, sr w1 -> retx 1"  sr $T/small.bin "--window 1 --drop-every 15" "--window 1" no "packets_sent=22 retransmissions=1 timeouts=1"
run "SR8b single loss, sr w4 -> retx 1"  sr $T/small.bin "--window 4 --drop-every 15" "--window 4" no "packets_sent=22 retransmissions=1 timeouts=1"
run "SR8c single loss, sr w8 -> retx 1"  sr $T/small.bin "--window 8 --drop-every 15" "--window 8" no "packets_sent=22 retransmissions=1 timeouts=1"
run "SR9 EOF lost, sr w8"                sr $T/f3000.bin "--window 8 --drop-every 4" "--window 8" no "packets_sent=5 retransmissions=1 timeouts=1"
run "SR10a final ACK lost, rto 1500"     sr $T/f3000.bin "--window 8 --rto 1500" "--window 8 --drop-every 5" no "retransmissions=1 timeouts=1"
run "SR10b final ACK lost, adaptive"     sr $T/f3000.bin "--window 8" "--window 8 --drop-every 5" no "retransmissions=1 timeouts=1"
for n in 0 1 1024 2048; do
  pk=$(( (n + 1023) / 1024 + 1 ))
  run "SR11 size $n B -> $pk pkts"         sr $T/f$n.bin "--window 4" "--window 4" no "packets_sent=$pk retransmissions=0"
done
run "SR12 window 32 > 4 packets"         sr $T/f3000.bin "--window 32" "--window 32" no "packets_sent=4 retransmissions=0"
run "SR13 receiver window < sender (4/8)" sr $T/big.bin "--window 8" "--window 4"

echo
echo "== Channel emulator end-to-end (200 KB, impairments on DATA and ACK paths) =="
# name | options for BOTH sides | expect retransmissions?
EMU=(
  "none|--seed 1|no"
  "loss 5%|--loss 0.05 --seed 11|yes"
  "loss 10%|--loss 0.10 --seed 12|yes"
  "corrupt 5%|--corrupt 0.05 --seed 13|yes"
  "reorder 10%|--reorder 0.10 --seed 14|no"
  "dup 10%|--dup 0.10 --seed 15|no"
  "delay 20+-5ms|--delay 20 --jitter 5 --seed 16|no"
  "combined|--loss 0.05 --dup 0.03 --reorder 0.05 --corrupt 0.03 --delay 10 --jitter 3 --seed 17|yes"
)
for e in "${EMU[@]}"; do
  IFS='|' read -r ename eopts eretx <<< "$e"
  run "EMU saw  $ename"   saw $T/mid.bin "$eopts"            "$eopts"            $eretx
  run "EMU gbn8 $ename"   gbn $T/mid.bin "--window 8 $eopts" "--window 8 $eopts" $eretx
  run "EMU sr8  $ename"   sr  $T/mid.bin "--window 8 $eopts" "--window 8 $eopts" $eretx
done

# T7 retry cap: everything lost -> both sides must give up (non-zero exit), not hang.
PORT=$((PORT + 1)); t0=$(date +%s)
timeout 60 ./server $PORT $T/f3000.bin --proto gbn --window 4 --rto 20 --drop-every 1 >$T/server_$PORT.log 2>&1 &
sp=$!; sleep 0.2
timeout 60 ./client 127.0.0.1 $PORT $T/out_$PORT.bin --proto gbn --window 4 >$T/client_$PORT.log 2>&1; cr=$?
wait $sp; sr=$?; dt=$(( $(date +%s) - t0 ))
if [ $sr -eq 1 ] && [ $cr -eq 1 ] && [ $dt -le 20 ]; then
    PASS=$((PASS + 1)); echo "PASS  T7 retry cap: both give up cleanly       server=1 client=1 in ${dt}s"
else
    FAIL=$((FAIL + 1)); echo "FAIL  T7 retry cap                       server=$sr client=$cr in ${dt}s"
fi

echo
echo "passed: $PASS   failed: $FAIL"
[ $FAIL -eq 0 ]
