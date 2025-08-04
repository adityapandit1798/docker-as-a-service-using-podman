// static/js/image-info.js - Enhanced Image Details Modal
// static/js/image-info.js

document.addEventListener("DOMContentLoaded", () => {
    const searchForm = document.getElementById("searchForm");
    const searchResults = document.getElementById("searchResults");

    searchForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const query = document.getElementById("searchInput").value.trim();

        if (!query) {
            alert("Please enter an image name.");
            return;
        }

        try {
            // Fetch search results
            const response = await fetch(`/api/docker-hub/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            if (!data.results || data.results.length === 0) {
                searchResults.innerHTML = "<p>No results found.</p>";
                return;
            }

            // Display results
            let html = "";
            for (const result of data.results.slice(0, 5)) {
                html += `
                    <div class="card mb-3">
                        <div class="card-body">
                            <h5 class="card-title">${result.namespace}/${result.name}</h5>
                            <p class="card-text">${result.description}</p>
                            <small class="text-muted">
                                Pulls: ${formatNumber(result.pull_count)} | 
                                Latest Tag: ${result.latest_tag} |
                                Size: ${formatBytes(result.size)}
                            </small>
                            <div class="mt-2">
                                <a href="#" class="btn btn-sm btn-success pull-btn" data-image="${result.namespace}/${result.name}">
                                    Pull latest
                                </a>
                                <a href="#" class="btn btn-sm btn-secondary pull-custom-btn" data-image="${result.namespace}/${result.name}">
                                    Pull custom tag...
                                </a>
                            </div>
                        </div>
                    </div>
                `;
            }

            searchResults.innerHTML = html;

            // Attach click handlers for "Pull latest" and "Pull custom tag..."
            document.querySelectorAll(".pull-btn").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const imageName = btn.getAttribute("data-image");
                    const tag = "latest";
                    // Call API to pull image
                    api_post(`/images/pull`, { repo: imageName, tag: tag });
                    alert(`Pulling ${imageName}:${tag}`);
                });
            });

            document.querySelectorAll(".pull-custom-btn").forEach(btn => {
                btn.addEventListener("click", () => {
                    const imageName = btn.getAttribute("data-image");
                    const tag = prompt("Enter tag name:", "latest");
                    if (tag) {
                        // Call API to pull specific tag
                        api_post(`/images/pull`, { repo: imageName, tag: tag });
                        alert(`Pulling ${imageName}:${tag}`);
                    }
                });
            });
        } catch (err) {
            searchResults.innerHTML = `<p class="text-danger">Error: ${err.message}</p>`;
        }
    });
});



function buildImageInfoHTML(repoData, tagData, imageName, tag) {
    const { full_description: descSections = {} } = repoData;

    return `
        <div class="mb-4">
            <div class="d-flex align-items-center mb-2">
                <h5 class="mb-0">${repoData.is_official ? '✅ ' : ''}<strong>${repoData.namespace}/${repoData.name}</strong></h5>
                ${repoData.is_official ? '<span class="badge bg-success ms-2">Official</span>' : ''}
            </div>
            <p class="text-muted">${repoData.description || 'No description'}</p>
            
            <div class="row g-3 small">
                <div class="col-md-4">
                    <strong>⭐ Stars:</strong> ${formatNumber(repoData.star_count)}
                </div>
                <div class="col-md-4">
                    <strong>📥 Pulls:</strong> ${formatNumber(repoData.pull_count)}
                </div>
                <div class="col-md-4">
                    <strong>Size:</strong> ${formatBytes(tagData.full_size || 0)}
                </div>
            </div>

            ${repoData.categories?.length ? `
            <div class="mt-2">
                <small>Categories: 
                    ${repoData.categories.map(c => `<span class="badge bg-secondary">${c.name}</span>`).join(" ")}
                </small>
            </div>
            ` : ''}
        </div>

        ${renderSection("Quick Reference", descSections["Quick reference"])}
        ${renderSection("Supported Tags", descSections["Supported tags and respective `Dockerfile` links"], true)}
        ${renderSection("What is nginx?", descSections["What is nginx?"])}
        ${renderSection("How to use this image", descSections["How to use this image"])}
        ${renderSection("Image Variants", descSections["Image Variants"])}

        <div class="mt-4 pt-3 border-top">
            <a href="https://hub.docker.com/r/${repoData.namespace}/${repoData.name}" 
               target="_blank" class="btn btn-sm btn-primary">
                Open on Docker Hub ↗
            </a>
        </div>
    `;
}

function renderSection(title, lines, isTags = false) {
    if (!lines || lines.length === 0) return '';

    let content = `<h6 class="mt-3">${title}</h6><ul class="list-unstyled mb-3">`;
    
    lines.slice(0, 8).forEach(line => {
        if (line.startsWith("```")) return;
        
        if (line.includes("http")) {
            const match = line.match(/(https?:\/\/[^\s]+)(?:\s+(.+))?/);
            if (match) {
                const url = match[1];
                const text = match[2] || url;
                line = line.replace(/https?:\/\/[^\s]+(\s+.+)?/, `<a href="${url}" target="_blank">${text}</a>`);
            }
        }

        if (isTags && line.includes("]")) {
            // Extract tag names and Dockerfile links
            const tagMatch = line.match(/\[(.+?)\]\((.+?)\)/);
            if (tagMatch) {
                const tagList = tagMatch[1].split(',').map(t => t.trim()).join(', ');
                const link = tagMatch[2];
                line = `<strong>Tags:</strong> ${tagList}<br>
                        <small><a href="${link}" target="_blank">Dockerfile ↗</a></small>`;
            }
        }

        content += `<li class="mb-1">${line}</li>`;
    });

    if (lines.length > 8) {
        content += `<li class="text-muted small">...and more</li>`;
    }

    return content + `</ul>`;
}

// Helper: Format numbers
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