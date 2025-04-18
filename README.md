# QUIC Trading Platform & Performance Scenarios

This repository contains a modular QUIC-based trading platform and three performance testing scenarios:

- **Multiple Streams**
- **Connection Migration**
- **Connection Establishment Overhead**
- **Order Matching Engine (Full Trading Platform)**

Each scenario is containerized and can be launched independently using Docker Compose.

---

## Prerequisites

- [Docker](https://www.docker.com/get-started) and [Docker Compose](https://docs.docker.com/compose/)
- (Optional) `docker-compose` v2+ recommended

---

## Directory Structure

```
FYP/
├── Multiple_Streams/
├── Connection_Migration/
├── Connection_Establishment_Overhead/
└── Order_Matching_Engine/
```

---

## 1. Multiple Streams

This scenario evaluates QUIC’s ability to handle multiple concurrent streams between client and server.

**To run:**
```sh
cd Multiple_Streams
docker-compose up --build
```

- The client and server containers will start automatically.
- You can configure the number of streams by setting the `NUM_STREAMS` environment variable:
  ```sh
  NUM_STREAMS=5 docker-compose up --build
  ```
- Logs and QUIC logs are available in the `qlogs/` directory.

---

## 2. Connection Migration

This scenario tests QUIC’s connection migration capabilities (e.g., simulating client IP changes).

**To run:**
```sh
cd ../Connection_Migration
docker-compose up --build
```

- The setup will launch both client and server.
- The client simulates migration events as part of its workflow.
- QUIC logs and captures are stored in the `qlogs/` and `capture/` directories.

---

## 3. Connection Establishment Overhead

This scenario measures the overhead of connection establishment and session resumption.

**To run:**
```sh
cd ../Connection_Establishment_Overhead
docker-compose up --build
```

- Includes a `tcpdump` container to capture network traces (`capture/`).
- Session tickets and SSL keys are mounted for analysis.
- All logs are saved in their respective directories.

---

## 4. Order Matching Engine (Full Trading Platform)

This is the main trading platform, supporting multiple clients, a matching engine, and web clients.

**To run:**
```sh
cd ../Order_Matching_Engine
docker-compose up --build
```

- Starts multiple clients, the matching engine, server, web clients, and a tcpdump container.
- Web UIs are accessible at:
  - [http://localhost:6060](http://localhost:6060) (Trader 1)
  - [http://localhost:6061](http://localhost:6061) (Trader 2)
- All QUIC and trading logs are available in `qlogs/` and `certs/`.

---

## Stopping the Environment

To stop and remove all containers for a scenario:
```sh
docker-compose down
```

---

## Notes

- Each scenario is self-contained; you can run them independently.
- Certificates are auto-generated and mounted as needed.
- For custom testing or debugging, modify the respective `client.py` or `server.py` scripts in each scenario folder.

---

If you have any issues or want to add more details (such as troubleshooting, environment variables, or deeper explanations of each scenario’s purpose), please open an issue or contact the maintainer.
