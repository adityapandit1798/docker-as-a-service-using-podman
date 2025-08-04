// static/js/search.js - Docker Hub Image Search with Button & Tag Info

searchBtn.addEventListener("click", async () => {
    const query = searchInput.value.trim();
    console.log("🖱️ Search button clicked. Query:", query);

    if (!query) {
        alert("Please enter an image name");
        return;
    }

    try {
        searchResults.innerHTML = '<div class="list-group-item">🔍 Searching Docker Hub...</div>';
        searchResults.style.display = "block";

        const result = await searchDockerHub(query);
        console.log("✅ Final search result:", result);
        displayResults(result, query);
    } catch (err) {
        console.error("🚨 Critical error during search:", err);
        searchResults.innerHTML = `
            <div class="list-group-item text-danger">
                <strong>Fetch Failed:</strong> ${err.message}
            </div>
            <small>Check console (F12) for details</small>
        `;
        searchResults.style.display = "block";
    }
});


async function searchDockerHub(query) {
    console.log("🔍 searchDockerHub called with:", query);

    try {
        // ✅ Call YOUR server, not Docker Hub directly
        const response = await fetch(`/api/docker-hub/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        console.log("✅ Proxy response:", data);
        return data;
    } catch (err) {
        console.error("🚨 Fetch error:", err);
        throw err;
    }
}

function displayResults(data, query) {
    const resultsEl = document.getElementById("searchResults");
    resultsEl.innerHTML = "";
    resultsEl.style.display = "none";

    // ✅ Safe check
    if (!data || !Array.isArray(data.results) || data.results.length === 0) {
        resultsEl.innerHTML = '<div class="list-group-item">No results found</div>';
        resultsEl.style.display = "block";
        return;
    }

    data.results.forEach(img => {
        // ✅ Guard against missing image data
        if (!img || !img.name || !img.namespace) {
            console.warn("Invalid image data:", img);
            return;
        }

        const item = document.createElement("a");
        item.href = "#";
        item.className = "list-group-item list-group-item-action";
        item.innerHTML = `
            <div class="d-flex justify-content-between">
                <h6 class="mb-1">
                    <strong>${img.namespace}/${img.name}</strong>
                    ${img.is_official ? '<span class="badge bg-success">Official</span>' : ''}
                </h6>
                <small class="text-muted">Pulls: ${formatNumber(img.pull_count || 0)}</small>
            </div>
            <p class="mb-1">${img.description || 'No description'}</p>
            <small>
                <strong>Latest Tag:</strong> ${img.tagInfo?.name || 'latest'} |
                <strong>Created:</strong> ${formatDate(img.tagInfo?.last_updated)} |
                <strong>Size:</strong> ${formatBytes(img.tagInfo?.full_size || 0)}
            </small>
            <div class="mt-2">
                <button class="btn btn-sm btn-outline-success pull-tag" 
                        data-image="${img.namespace}/${img.name}:latest">
                    Pull latest
                </button>
                <button class="btn btn-sm btn-outline-secondary pull-custom" 
                        data-image="${img.namespace}/${img.name}">
                    Pull custom tag...
                </button>
            </div>
        `;
        resultsEl.appendChild(item);
    });

    attachPullHandlers();
    resultsEl.style.display = "block";
}

function attachPullHandlers() {
    document.querySelectorAll(".pull-tag").forEach(btn => {
        btn.onclick = (e) => {
            e.preventDefault();
            const image = e.target.getAttribute("data-image");
            pullImage(image);
        };
    });

    document.querySelectorAll(".pull-custom").forEach(btn => {
        btn.onclick = (e) => {
            e.preventDefault();
            const imageBase = e.target.getAttribute("data-image");
            const tag = prompt("Enter tag to pull:", "latest");
            if (tag) {
                pullImage(`${imageBase}:${tag}`);
            }
        };
    });
}

// Helper: Format large numbers
function formatNumber(num) {
    if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + "M";
    if (num >= 1_000) return (num / 1_000).toFixed(1) + "K";
    return num.toString();
}

// Helper: Format bytes
function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

// Helper: Format date
function formatDate(isoDate) {
    if (!isoDate) return "Unknown";
    return new Date(isoDate).toLocaleDateString();
}

// Pull image via POST
async function pullImage(imageName) {
    if (!confirm(`Pull image: ${imageName}? This may take a moment.`)) return;

    const [repo, tag] = imageName.split(":");

    const formData = new URLSearchParams();
    formData.append("repo", repo);
    formData.append("tag", tag || "latest");

    try {
        const response = await fetch("/images/pull", {
            method: "POST",
            body: formData,
            headers: { "Content-Type": "application/x-www-form-urlencoded" }
        });

        if (response.redirected || response.status === 200) {
            alert(`${imageName} pull started!`);
            setTimeout(() => location.reload(), 2000);
        } else {
            alert("Failed to start pull.");
        }
    } catch (err) {
        alert("Error: " + err.message);
    }
}