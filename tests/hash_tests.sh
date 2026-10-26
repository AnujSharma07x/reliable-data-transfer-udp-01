#!/usr/bin/env bash
# hash_tests.sh - file-level integrity (SHA-256) through the real channel emulator.
#
# Every row checks, independently of our C code:
#   - server source_sha256   == coreutils sha256sum(source file)
#   - client received_sha256 == coreutils sha256sum(output file actually written)
#   - client hash_match / exit code as expected
#   - output is byte-identical to the source (cmp), file_bytes == file size
# Negative rows give the client a WRONG expected hash (source with 1 bit
# flipped / 1 byte missing) and require hash_match=0 + exit code 2, while the
# transfer itself is still correct - proving the comparison is meaningful.
cd "$(dirname "$0")/.." || exit 1
T=tests/tmp/hash
mkdir -p $T
PORT=${BASE_PORT:-9400}
PASS=0; FAIL=0; ROWS=$T/hash_results.txt
EXPECTED_ROWS=43   # transfer rows below: 18 + 3 + 3 + 6 + 9 + 4
: > $ROWS

python3 - "$T" <<'EOF'
import random, sys
T = sys.argv[1]
for name, n, seed in [("empty", 0, 1), ("one", 1, 2), ("small", 500, 3), ("exact", 1024, 4),
                      ("multi", 20000, 5), ("mid", 200000, 6), ("mb", 1048576, 7),
                      ("large", 8388608, 8)]:
    open(f"{T}/{name}.bin", "wb").write(random.Random(seed).randbytes(n))
mid = bytearray(open(f"{T}/mid.bin", "rb").read())
mid[100000] ^= 0x01                                   # one bit flipped
open(f"{T}/mid_bitflip.bin", "wb").write(mid)
open(f"{T}/mid_short.bin", "wb").write(open(f"{T}/mid.bin", "rb").read()[:-1])  # 1 byte missing
EOF

sha() { sha256sum "$1" | cut -d' ' -f1; }
field() { echo " $1 " | sed -n "s/.* $2=\([^ ]*\) .*/\1/p"; }
# packets corrupted by the emulator (0 if no CHANNEL line: no impairment configured)
chan_corrupt() { local c; c=$(sed -n 's/^CHANNEL .*corrupted=\([0-9]*\).*/\1/p' "$1"); echo "${c:-0}"; }

NONE="--seed 1"
LOSS="--loss 0.10 --seed 21"
CORR="--corrupt 0.10 --seed 22"
COMB="--loss 0.05 --dup 0.05 --reorder 0.05 --corrupt 0.05 --delay 5 --jitter 2 --seed 23"

# hrun <id> <proto> <file> <emu-name> [expected-hash] [want_match] [want_client_exit] [need_retx] [need_corrupt]
hrun() {
    local id=$1 proto=$2 f=$3 ename=$4 exp=${5:-} want=${6:-1} wantc=${7:-0}
    local needr=${8:-no} needc=${9:-no} emu=${!4} w=""
    [ "$proto" != saw ] && w="--window 8"
    PORT=$((PORT + 1))
    local out=$T/out_$PORT.bin slog=$T/s_$PORT.log clog=$T/c_$PORT.log ref
    ref=$(sha "$f"); [ -z "$exp" ] && exp=$ref

    timeout 180 ./server $PORT "$f" --proto $proto $w $emu >"$slog" 2>&1 &
    local sp=$!
    sleep 0.2
    timeout 180 ./client 127.0.0.1 $PORT "$out" --proto $proto $w $emu --expect-sha256 "$exp" >"$clog" 2>&1
    local ce=$?
    wait $sp
    local se=$?

    local res recv src rcv match retx sent fb size rc_det sc_det ch why=""
    res=$(grep '^RESULT' "$slog"); recv=$(grep '^RECV' "$clog")
    src=$(field "$res" source_sha256); rcv=$(field "$recv" received_sha256)
    match=$(field "$recv" hash_match); retx=$(field "$res" retransmissions)
    sent=$(field "$res" packets_sent); fb=$(field "$res" file_bytes); size=$(stat -c %s "$f")
    rc_det=$(field "$recv" corrupted); sc_det=$(field "$res" corrupted)        # checksum failures seen
    ch=$(( $(chan_corrupt "$slog") + $(chan_corrupt "$clog") ))   # corrupted by emulator

    [ "$se" -eq 0 ]               || why="$why server_exit=$se"
    [ "$ce" -eq "$wantc" ]        || why="$why client_exit=$ce"
    [ "$src" = "$ref" ]           || why="$why source_sha256!=sha256sum(source)"
    [ -f "$out" ] && [ "$rcv" = "$(sha "$out")" ] || why="$why received_sha256!=sha256sum(output)"
    [ "$match" = "$want" ]        || why="$why hash_match=$match"
    cmp -s "$f" "$out"            || why="$why output!=source"
    [ "$fb" = "$size" ]           || why="$why file_bytes=$fb!=size=$size"
    if [ "$want" = 1 ]; then [ "$rcv" = "$src" ] || why="$why received!=source"; fi
    if [ "$needr" = yes ] && [ "${retx:-0}" -eq 0 ]; then why="$why no_retransmissions"; fi
    if [ "$needc" = yes ] && { [ "$ch" -eq 0 ] || [ $(( ${rc_det:-0} + ${sc_det:-0} )) -eq 0 ]; }; then
        why="$why no_corruption_detected"; fi

    local verdict=PASS
    [ -n "$why" ] && verdict=FAIL
    [ $verdict = PASS ] && PASS=$((PASS + 1)) || FAIL=$((FAIL + 1))
    printf "%-4s %-4s %-3s %8s B  %-8s src=%.12s rcv=%.12s match=%s exit=%s/%s sent=%-5s retx=%-4s corrupt(emu/detected)=%s/%s%s\n" \
        $verdict "$id" "$proto" "$size" "$ename" "$src" "$rcv" "$match" "$se" "$ce" "$sent" "$retx" \
        "$ch" $(( ${rc_det:-0} + ${sc_det:-0} )) "${why:+  <-$why}"
    echo "$verdict,$id,$proto,$size,$ename,$src,$rcv,$match,$se,$ce,$sent,$retx" >> $ROWS
    LAST="$sent/$retx/$src/$rcv"
}

echo "== H1-H6: file sizes, all protocols, no impairment =="
for p in saw gbn sr; do
    hrun H1 $p $T/empty.bin NONE
    hrun H2 $p $T/one.bin   NONE
    hrun H3 $p $T/small.bin NONE
    hrun H4 $p $T/exact.bin NONE
    hrun H5 $p $T/multi.bin NONE
    hrun H6 $p $T/large.bin NONE
done
echo "== H7-H9: 1 MB, no impairment =="
hrun H7 saw $T/mb.bin NONE
hrun H8 gbn $T/mb.bin NONE
hrun H9 sr  $T/mb.bin NONE
echo "== H10-H12: 1 MB, 10% loss on both paths =="
hrun H10 saw $T/mb.bin LOSS "" 1 0 yes
hrun H11 gbn $T/mb.bin LOSS "" 1 0 yes
hrun H12 sr  $T/mb.bin LOSS "" 1 0 yes
echo "== H13: corruption through the real emulator (checksum -> retransmit -> hash) =="
for p in saw gbn sr; do hrun H13 $p $T/mb.bin CORR "" 1 0 yes yes; done
for p in saw gbn sr; do hrun H13c $p $T/mb.bin COMB "" 1 0 yes yes; done

echo "== H14: repeatability under combined impairments (3 runs each) =="
for p in saw gbn sr; do
    runs=()
    for r in 1 2 3; do hrun H14 $p $T/mid.bin COMB "" 1 0 yes; runs+=("$LAST"); done
    # Each hrun independently checks source/output SHA-256, hash_match, byte
    # identity and process exit codes. Do not require equal retransmission
    # counts: real-time RTO scheduling can vary even with the same PRNG seed.
    src0=$(echo "${runs[0]}" | cut -d/ -f3); rcv0=$(echo "${runs[0]}" | cut -d/ -f4)
    src1=$(echo "${runs[1]}" | cut -d/ -f3); rcv1=$(echo "${runs[1]}" | cut -d/ -f4)
    src2=$(echo "${runs[2]}" | cut -d/ -f3); rcv2=$(echo "${runs[2]}" | cut -d/ -f4)
    if [ -n "$src0" ] && [ "$src0" = "$src1" ] && [ "$src1" = "$src2" ] \
       && [ "$rcv0" = "$src0" ] && [ "$rcv1" = "$src1" ] && [ "$rcv2" = "$src2" ]; then
        PASS=$((PASS + 1)); printf "PASS H14  %s: all 3 transfers preserve identical source/output SHA-256; sent/retx=%s/%s, %s/%s, %s/%s\n" \
            "$p" "$(echo "${runs[0]}" | cut -d/ -f1)" "$(echo "${runs[0]}" | cut -d/ -f2)" \
            "$(echo "${runs[1]}" | cut -d/ -f1)" "$(echo "${runs[1]}" | cut -d/ -f2)" \
            "$(echo "${runs[2]}" | cut -d/ -f1)" "$(echo "${runs[2]}" | cut -d/ -f2)"
    else
        FAIL=$((FAIL + 1)); echo "FAIL H14  $p: repeated transfer hashes differ: ${runs[*]}"
    fi
done

echo "== N1-N2: wrong expected hash must be detected (transfer itself still correct) =="
for p in saw gbn sr; do hrun N1 $p $T/mid.bin NONE "$(sha $T/mid_bitflip.bin)" 0 2; done
hrun N2 sr $T/mid.bin COMB "$(sha $T/mid_short.bin)" 0 2

echo "== B1: without --expect-sha256 (backward compatible) =="
PORT=$((PORT + 1))
./server $PORT $T/mid.bin --proto sr --window 8 >$T/b1s.log 2>&1 &
sp=$!; sleep 0.2
./client 127.0.0.1 $PORT $T/b1o.bin --proto sr --window 8 >$T/b1c.log 2>&1; ce=$?
wait $sp; se=$?
b1=$(grep '^RECV' $T/b1c.log)
if [ $se -eq 0 ] && [ $ce -eq 0 ] && [ "$(field "$b1" received_sha256)" = "$(sha $T/mid.bin)" ] \
   && ! echo "$b1" | grep -q hash_match; then
    PASS=$((PASS + 1)); echo "PASS B1   received_sha256 reported, no hash_match field, exit 0"
else
    FAIL=$((FAIL + 1)); echo "FAIL B1   $b1 (exit $se/$ce)"
fi

echo "== H15: byte-for-byte + completeness =="
n=$(grep -c . $ROWS)
if [ "$n" -eq $EXPECTED_ROWS ]; then
    PASS=$((PASS + 1)); echo "PASS H15  all $n transfer rows ran, each required cmp(source, output) == identical"
else
    FAIL=$((FAIL + 1)); echo "FAIL H15  only $n of $EXPECTED_ROWS transfer rows completed (a row aborted)"
fi

echo
echo "hash tests passed: $PASS   failed: $FAIL   (full hashes: $ROWS)"
[ $FAIL -eq 0 ]
