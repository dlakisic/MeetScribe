# MeetScribe Deployment Guide 🚀

This guide explains how to deploy MeetScribe on a **Split Architecture**:
1.  **Server (Always-On)**: Use your N100 Mini-PC.
2.  **Worker (On-Demand)**: Use your RTX 4070 PC.

## Architecture

*   **Server (N100)**: Runs the API (`:8090`) and Database. Accessible by the Chrome Extension.
*   **Worker (4070)**: Runs the GPU transcription service (`:8001`). Only needs to be on during meetings.

---

## 1. Setup Server (N100)

**On the N100 machine (`192.168.1.XX`):**

1.  Clone the repo:
    ```bash
    git clone git@github.com:dlakisic/MeetScribe.git
    cd MeetScribe/infra/server
    ```

2.  Configure Environment:
    ```bash
    cp .env.example .env
    nano .env
    ```
    *   **CRITICAL**: Set `GPU_HOST` to the IP address of your 4070 PC (e.g., `192.168.1.20`).
    *   Set `APP_PORT` to `8090` (default) or another free port.

3.  Start the Server:
    ```bash
    docker-compose up -d --build
    ```

4.  **Verify**: Open `http://192.168.1.XX:8090/health` in your browser.

---

## 2. Setup Worker (RTX 4070 PC)

**On the 4070 PC:**

1.  Clone the repo:
    ```bash
    git clone git@github.com:dlakisic/MeetScribe.git
    cd MeetScribe/infra/worker
    ```

2.  Start the Worker:
    *   *Prerequisite*: Ensure Docker Desktop (Windows) or Docker Engine (Linux) is installed with **NVIDIA Container Toolkit** support.
    
    ```bash
    docker-compose up -d --build
    ```

3.  **Verify**: Open `http://localhost:8001/health`.

---

## 3. Connect Chrome Extension

1.  Open Chrome Extension settings (or `main.js` if hardcoded for now).
2.  Point the **API URL** to: `http://192.168.1.XX:8090`.

## Troubleshooting

-   **Backend cannot reach Worker**:
    -   Check if 4070 PC firewall allows port `8001`.
    -   Verify `GPU_HOST` in `.env` on N100 matches 4070 IP.
-   **GPU not found**:
    -   Ensure `nvidia-smi` works inside the container:
        ```bash
        docker compose exec worker nvidia-smi
        ```
