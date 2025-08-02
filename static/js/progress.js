// static/js/progress.js
class ProgressModal {
    constructor() {
        this.modal = new bootstrap.Modal(document.getElementById("progressModal"));
        this.statusEl = document.getElementById("progressStatus");
        this.barEl = document.getElementById("progressBar");
        this.logsEl = document.getElementById("progressLogs");
    }

    show(title) {
        this.statusEl.textContent = "Starting...";
        this.barEl.style.width = "0%";
        this.logsEl.style.display = "none";
        this.logsEl.textContent = "";
        document.querySelector("#progressModal .modal-title").textContent = title;
        this.modal.show();
    }

    update(status, progress = null, log = null) {
        this.statusEl.textContent = status;
        if (progress !== null) {
            this.barEl.style.width = `${progress}%`;
        }
        if (log) {
            this.logsEl.style.display = "block";
            this.logsEl.textContent += log + "\n";
            this.logsEl.scrollTop = this.logsEl.scrollHeight;
        }
    }

    close() {
        setTimeout(() => this.modal.hide(), 2000);
    }
}

async function streamImagePull(imageName, onSuccess = () => {}) {
    const modal = new ProgressModal();
    modal.show(`Pulling ${imageName}`);

    try {
        const response = await fetch(`/images/pull-stream?image=${encodeURIComponent(imageName)}`);
        if (!response.body) throw new Error("No stream");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split("\n");
            buffer = lines.pop();

            for (let line of lines) {
                if (!line.trim()) continue;
                try {
                    let event = JSON.parse(line);
                    let status = event.status || event.error || "Processing";
                    let progress = event.progressDetail ?
                        Math.round((event.progressDetail.current || 0) * 100 / (event.progressDetail.total || 1)) :
                        null;

                    modal.update(status, progress, event.stream || null);

                    if (event.error) {
                        alert("❌ " + event.error);
                        modal.close();
                        return;
                    }
                } catch (e) {
                    console.warn("Parse error:", line);
                }
            }
        }
        modal.update("✅ Pull Complete!", 100);
        modal.close();
        onSuccess();
    } catch (err) {
        modal.update(`❌ Failed: ${err.message}`, 0);
        setTimeout(() => modal.modal.hide(), 3000);
    }
}