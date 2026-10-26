CC      = gcc
CFLAGS  = -std=gnu11 -Wall -Wextra -O2 -Isrc -pthread
LDLIBS  = -lm -pthread -lcrypto

COMMON  = src/packet.o src/net.o src/channel.o src/rto.o src/arq.o \
          src/options.o src/saw.o src/gbn.o src/sr.o src/hash.o

all: server client test_units test_channel

server: src/server.o $(COMMON)
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

client: src/client.o $(COMMON)
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

test_units: tests/test_units.o src/packet.o src/rto.o src/hash.o
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

test_channel: tests/test_channel.o src/channel.o src/packet.o
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

src/%.o: src/%.c src/*.h
	$(CC) $(CFLAGS) -c -o $@ $<

tests/%.o: tests/%.c src/*.h
	$(CC) $(CFLAGS) -c -o $@ $<

test: all
	./test_units
	./test_channel
	./tests/run_tests.sh
	python3 tests/gbn_packet_tests.py
	python3 tests/sr_packet_tests.py
	./tests/hash_tests.sh

clean:
	rm -f src/*.o tests/*.o server client test_units test_channel
	rm -rf tests/tmp

.PHONY: all test clean
