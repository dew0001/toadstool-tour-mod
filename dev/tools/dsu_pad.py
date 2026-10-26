"""A virtual controller for the test Dolphin, so tests never need the real keyboard, mouse or screen focus.

Speaks the DSU ("cemuhook") protocol that Dolphin's DSU Client reads (Config/DSUClient.ini), and takes commands
on a local TCP port. test_dolphin.ps1 maps the test profile's GameCube pad (and the screenshot hotkey) to it.

  python -I dsu_pad.py serve                 run the server (UDP 26760 for Dolphin, TCP 26761 for commands)
  python -I dsu_pad.py press Cross [ms]      hold a button (default 150 ms), then let go
  python -I dsu_pad.py hold Cross | release Cross | release all
  python -I dsu_pad.py stick L 0 1 [ms]      left/right stick to x, y in -1..1 (for ms, then back to centre)
  python -I dsu_pad.py seq "Cross 150; wait 2000; Pad E 150; ..."   a sequence, run in order
  python -I dsu_pad.py status

Buttons: Pad N/S/E/W, Cross, Circle, Square, Triangle, L1, R1, L2, R2, L3, R3, Share, Options, PS, Touch.
Test-profile mapping (test_dolphin.ps1): A = Cross, B = Circle, X = Square, Y = Triangle, Z = R1, Start = Share,
L/R = L2/R2, main stick = left stick, C-stick = right stick, D-pad = Pad N/S/E/W, screenshot = PS.
"""
import json
import random
import socket
import struct
import sys
import threading
import time
import zlib

DSU_PORT, CMD_PORT = 26760, 26761
PROTOCOL = 1001
MSG_VERSION, MSG_PORTS, MSG_DATA = 0x100000, 0x100001, 0x100002
BUTTONS1 = {"Pad W": 0x80, "Pad S": 0x40, "Pad E": 0x20, "Pad N": 0x10, "Options": 0x08, "R3": 0x04, "L3": 0x02,
            "Share": 0x01}
BUTTONS2 = {"Square": 0x80, "Cross": 0x40, "Circle": 0x20, "Triangle": 0x10, "R1": 0x08, "L1": 0x04, "R2": 0x02,
            "L2": 0x01}
SPECIAL = {"PS", "Touch"}
ALL_BUTTONS = set(BUTTONS1) | set(BUTTONS2) | SPECIAL
MAC = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])


class Pad:
    def __init__(self):
        self.lock = threading.Lock()
        self.held = set()
        self.sticks = {"L": (0.0, 0.0), "R": (0.0, 0.0)}

    def snapshot(self):
        with self.lock:
            return set(self.held), dict(self.sticks)


def packet(server_id, msg_type, body):
    length = 4 + len(body)
    head = b"DSUS" + struct.pack("<HHII", PROTOCOL, length, 0, server_id)
    data = head + struct.pack("<I", msg_type) + body
    crc = zlib.crc32(data) & 0xFFFFFFFF
    return data[:8] + struct.pack("<I", crc) + data[12:]


def shared(slot):
    if slot != 0:
        return struct.pack("<BBBB6sB", slot, 0, 0, 0, bytes(6), 0)
    return struct.pack("<BBBB6sB", 0, 2, 2, 1, MAC, 5)  # connected, full gyro, USB, battery full


def axis(v):
    return max(0, min(255, int(round(128 + v * 127))))


def data_body(pad, number):
    held, sticks = pad.snapshot()
    b1 = sum(bit for name, bit in BUTTONS1.items() if name in held)
    b2 = sum(bit for name, bit in BUTTONS2.items() if name in held)
    lx, ly = sticks["L"]
    rx, ry = sticks["R"]
    analog = lambda name: 255 if name in held else 0
    body = shared(0) + struct.pack("<BIBBBB", 1, number, b1, b2, int("PS" in held), int("Touch" in held))
    body += bytes([axis(lx), axis(ly), axis(rx), axis(ry)])
    body += bytes([analog("Pad W"), analog("Pad S"), analog("Pad E"), analog("Pad N")])
    body += bytes([analog("Square"), analog("Cross"), analog("Circle"), analog("Triangle")])
    body += bytes([analog("R1"), analog("L1"), analog("R2"), analog("L2")])
    body += bytes(12)  # two touches, inactive
    body += struct.pack("<Q", int(time.time() * 1e6)) + struct.pack("<6f", 0.0, 1.0, 0.0, 0.0, 0.0, 0.0)
    return body


def serve():
    pad = Pad()
    server_id = random.getrandbits(32)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(("127.0.0.1", DSU_PORT))
    clients = {}  # address -> last request time
    number = [0]

    def receive():
        while True:
            data, addr = udp.recvfrom(1024)
            if len(data) < 20 or data[:4] != b"DSUC":
                continue
            msg = struct.unpack_from("<I", data, 16)[0]
            if msg == MSG_VERSION:
                udp.sendto(packet(server_id, MSG_VERSION, struct.pack("<HH", PROTOCOL, 0)), addr)
            elif msg == MSG_PORTS:
                count = struct.unpack_from("<i", data, 20)[0]
                for slot in data[24:24 + max(0, min(count, 4))]:
                    udp.sendto(packet(server_id, MSG_PORTS, shared(slot) + b"\x00"), addr)
            elif msg == MSG_DATA:
                clients[addr] = time.time()

    def stream():
        while True:
            now = time.time()
            for addr, seen in list(clients.items()):
                if now - seen > 5:
                    del clients[addr]
                    continue
                number[0] += 1
                udp.sendto(packet(server_id, MSG_DATA, data_body(pad, number[0])), addr)
            time.sleep(0.004)

    def run_command(line):
        parts = line.strip().split()
        if not parts:
            return "empty"
        verb, args = parts[0].lower(), parts[1:]
        if verb == "status":
            held, sticks = pad.snapshot()
            return json.dumps({"held": sorted(held), "sticks": sticks, "clients": [f"{a[0]}:{a[1]}" for a in clients]})
        if verb == "wait":
            time.sleep(float(args[0]) / 1000)
            return "ok"
        if verb == "stick":
            which, x, y = args[0].upper(), float(args[1]), float(args[2])
            with pad.lock:
                pad.sticks[which] = (x, y)
            if len(args) > 3:
                time.sleep(float(args[3]) / 1000)
                with pad.lock:
                    pad.sticks[which] = (0.0, 0.0)
            return "ok"
        if verb == "release" and args and args[0].lower() == "all":
            with pad.lock:
                pad.held.clear()
                pad.sticks = {"L": (0.0, 0.0), "R": (0.0, 0.0)}
            return "ok"
        ms = None
        if args and args[-1].replace(".", "").isdigit():
            ms = float(args[-1])
            args = args[:-1]
        name = " ".join(args)
        if verb not in ("press", "hold", "release") or name not in ALL_BUTTONS:
            return f"unknown: {line.strip()}"
        if verb == "hold":
            with pad.lock:
                pad.held.add(name)
        elif verb == "release":
            with pad.lock:
                pad.held.discard(name)
        else:
            with pad.lock:
                pad.held.add(name)
            time.sleep((ms if ms is not None else 150) / 1000)
            with pad.lock:
                pad.held.discard(name)
        return "ok"

    def commands():
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind(("127.0.0.1", CMD_PORT))
        tcp.listen(4)
        while True:
            conn, _ = tcp.accept()
            with conn:
                text = b""
                while not text.endswith(b"\n"):
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    text += chunk
                replies = [run_command(part) for part in text.decode().split(";") if part.strip()]
                conn.sendall(("\n".join(replies) + "\n").encode())

    threading.Thread(target=receive, daemon=True).start()
    threading.Thread(target=stream, daemon=True).start()
    print(f"DSU pad: Dolphin on udp 127.0.0.1:{DSU_PORT}, commands on tcp 127.0.0.1:{CMD_PORT}", flush=True)
    commands()


def send(text):
    with socket.create_connection(("127.0.0.1", CMD_PORT), timeout=120) as s:
        s.sendall((text + "\n").encode())
        reply = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            reply += chunk
    return reply.decode().strip()


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    verb = sys.argv[1].lower()
    if verb == "serve":
        serve()
    elif verb == "seq":
        steps = []
        for step in sys.argv[2].split(";"):
            step = step.strip()
            if not step:
                continue
            first = step.split()[0].lower()
            steps.append(step if first in ("wait", "stick", "hold", "release", "status", "press") else "press " + step)
        print(send("; ".join(steps)))
    else:
        print(send(" ".join(sys.argv[1:])))


if __name__ == "__main__":
    main()
