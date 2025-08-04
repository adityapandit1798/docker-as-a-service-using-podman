# app.py - Docker as a Service (DaaS) - With Debugging & Fixed Volume/Network Selection
from flask import Flask, render_template, request, redirect, url_for, Response
import json
import os
import subprocess
import requests
import logging
from datetime import datetime
import yaml
import re
from flask import request
from werkzeug.utils import secure_filename
import tempfile


# 🔧 Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 🔗 Podman API Endpoint
PODMAN_API = "http://192.168.192.155:2375"


def api_get(endpoint):
    url = f"{PODMAN_API}{endpoint}"
    logger.info(f"GET {url}")
    try:
        response = requests.get(url, timeout=5)
        logger.info(f"Status: {response.status_code}, Body (truncated): {response.text[:200]}")
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"GET {url} -> {response.status_code}: {response.text}")
            return []
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection refused: {url}")
        return []
    except requests.exceptions.Timeout:
        logger.error(f"Request timeout: {url}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {str(e)}")
        return []


def api_post(endpoint, json=None):
    url = f"{PODMAN_API}{endpoint}"
    logger.info(f"POST {url}, JSON: {json}")
    try:
        response = requests.post(url, json=json, timeout=10)
        logger.info(f"Status: {response.status_code}, Body: {response.text}")
        return response
    except Exception as e:
        logger.error(f"POST {url} failed: {str(e)}")
        return None


def api_delete(endpoint):
    url = f"{PODMAN_API}{endpoint}"
    logger.info(f"DELETE {url}")
    try:
        response = requests.delete(url, timeout=10)
        logger.info(f"Status: {response.status_code}, Body: {response.text}")
        return response
    except Exception as e:
        logger.error(f"DELETE {url} failed: {str(e)}")
        return None


@app.route("/")
def index():
    logger.info("Rendering index page")

    containers = api_get("/containers/json?all=true")
    raw_images = api_get("/images/json")
    raw_volumes = api_get("/volumes")
    raw_networks = api_get("/networks")
    info = api_get("/info")

    # Process images
    images = []
    for img in raw_images:
        repotag = img["RepoTags"][0] if img.get("RepoTags") and len(img["RepoTags"]) > 0 else "<none>:<none>"
        size_mb = round(img["Size"] / 1024 / 1024, 1) if "Size" in img else 0
        images.append((img["Id"], repotag, size_mb))

    # Process volumes
    volumes = raw_volumes.get("Volumes", []) if isinstance(raw_volumes, dict) else []
    if volumes is None:
        volumes = []
    logger.info(f"Found {len(volumes)} volumes: {[v['Name'] for v in volumes]}")

    # Process networks
    networks = raw_networks if isinstance(raw_networks, list) else []
    if not networks and isinstance(raw_networks, dict):
        networks = [raw_networks] if "Name" in raw_networks else []
    logger.info(f"Found {len(networks)} networks: {[n['Name'] for n in networks]}")

    return render_template("index.html",
                           containers=containers,
                           images=images,
                           volumes=volumes,
                           networks=networks,
                           info=info)


# 🧱 Container Actions
@app.route("/containers/start/<cid>")
def start_container(cid):
    logger.info(f"Starting container {cid}")
    resp = api_post(f"/containers/{cid}/start")
    if resp and resp.status_code in [200, 204]:
        logger.info(f"Container {cid} started")
    else:
        logger.error(f"Failed to start {cid}")
    return redirect(url_for("index"))


@app.route("/containers/stop/<cid>")
def stop_container(cid):
    logger.info(f"Stopping container {cid}")
    resp = api_post(f"/containers/{cid}/stop")
    if resp and resp.status_code in [200, 204]:
        logger.info(f"Container {cid} stopped")
    return redirect(url_for("index"))


@app.route("/containers/remove/<cid>")
def remove_container(cid):
    logger.info(f"Removing container {cid}")
    # ✅ Use DELETE, not POST
    resp = api_delete(f"/containers/{cid}?v=true&force=true")
    if resp and resp.status_code == 204:
        logger.info(f"Container {cid} removed successfully")
    else:
        logger.error(f"Failed to remove container {cid}: {resp.text if resp else 'No response'}")
    return redirect(url_for("index"))

@app.route("/containers/logs/<cid>")
def view_logs(cid):
    logger.info(f"Fetching logs for {cid}")
    params = {"stdout": "true", "stderr": "true", "tail": "200"}
    try:
        response = requests.get(f"{PODMAN_API}/containers/{cid}/logs", params=params, timeout=5)
        logs = response.text or "No logs"
    except Exception as e:
        logs = f"Error fetching logs: {str(e)}"
        logger.error(f"Log fetch failed for {cid}: {e}")
    return render_template("logs.html", cid=cid, logs=logs)

# @app.route("/images/pull-stream")
# def pull_image_stream():
#     image = request.args.get("image", "alpine:latest")
#     url = f"{PODMAN_API}/images/create?fromImage={image}"

#     try:
#         r = requests.get(url, stream=True, timeout=60)
        
#         def generate():
#             for chunk in r.iter_lines():
#                 if chunk:
#                     yield chunk + b"\n"  # Must end with \n

#         return Response(
#             generate(),
#             content_type="application/json",
#             headers={
#                 "Transfer-Encoding": "chunked",
#                 "Cache-Control": "no-cache",
#                 "Connection": "keep-alive"
#             }
#         )
#     except Exception as e:
#         error = json.dumps({"error": str(e)}) + "\n"
#         return Response(error, content_type="application/json", status=500)

#📦 Image Actions
@app.route("/images/pull", methods=["POST"])
def pull_image():
    repo = request.form.get("repo", "").strip()
    tag = request.form.get("tag", "latest").strip()
    if not repo:
        logger.warning("Pull image: no repo provided")
        return redirect(url_for("index"))

    full_name = f"{repo}:{tag}" if tag else repo
    logger.info(f"Pulling image: {full_name}")
    resp = api_post(f"/images/create?fromImage={full_name}")

    if resp and resp.status_code in [200, 201]:
        logger.info(f"Image {full_name} pulled successfully")
    else:
        logger.error(f"Failed to pull {full_name}")
    return redirect(url_for("index"))


@app.route("/images/remove/<image_id>")
def remove_image(image_id):
    logger.info(f"Removing image {image_id}")
    resp = api_delete(f"/images/{image_id}?force=true")
    if resp and resp.status_code in [200, 204]:
        logger.info(f"Image {image_id} removed")
    else:
        logger.error(f"Failed to remove image {image_id}")
    return redirect(url_for("index"))


@app.route("/images/prune")
def prune_images():
    logger.info("Pruning unused images")
    resp = api_post("/images/prune")
    if resp and resp.status_code == 200:
        logger.info("Image pruning completed")
    return redirect(url_for("index"))


# 📁 Volume Actions
@app.route("/volumes/create", methods=["POST"])
def create_volume():
    name = request.form.get("name", "").strip()
    if not name:
        logger.warning("Create volume: no name provided")
        return redirect(url_for("index"))

    logger.info(f"Creating volume: {name}")
    resp = api_post("/volumes/create", json={"Name": name})
    if resp and resp.status_code == 201:
        logger.info(f"Volume {name} created")
    else:
        logger.error(f"Failed to create volume {name}")
    return redirect(url_for("index"))


@app.route("/volumes/remove/<vol_name>")
def remove_volume(vol_name):
    logger.info(f"Removing volume {vol_name}")
    resp = api_delete(f"/volumes/{vol_name}")
    if resp and resp.status_code in [200, 204]:
        logger.info(f"Volume {vol_name} removed")
    else:
        logger.error(f"Failed to remove volume {vol_name}")
    return redirect(url_for("index"))


@app.route("/compose/deploy", methods=["GET", "POST"])
def deploy_compose():
    if request.method == "POST":
        # Get YAML from form
        compose_text = request.form.get("compose_yaml", "").strip()
        if not compose_text:
            return "<script>alert('No compose file provided'); history.back();</script>"

        try:
            compose = yaml.safe_load(compose_text)
        except yaml.YAMLError as e:
            return f"<script>alert('Invalid YAML: {str(e)}'); history.back();</script>"

        # --- Step 1: Create Networks ---
        networks = compose.get("networks", {})
        for name, config in networks.items():
            if config is None:
                config = {}
            payload = {
                "Name": name,
                "Driver": config.get("driver", "bridge"),
                "CheckDuplicate": True
            }
            resp = api_post("/networks/create", json=payload)
            if resp and resp.status_code in [201, 200]:
                logger.info(f"Network '{name}' created or already exists")
            else:
                logger.error(f"Failed to create network '{name}': {resp.text if resp else 'No response'}")

        # --- Step 2: Process Services ---
        services = compose.get("services", {})
        for service_name, svc in services.items():
            if not svc.get("image"):
                logger.warning(f"Service '{service_name}' has no image, skipping")
                continue

            image = svc["image"]

            # Pull image
            logger.info(f"Pulling image: {image}")
            pull_resp = api_post(f"/images/create?fromImage={image}")
            if pull_resp and pull_resp.status_code in [200, 201]:
                logger.info(f"Image {image} pulled")
            else:
                logger.error(f"Failed to pull {image}")
                continue

            # --- Port Bindings ---
            # --- Port Bindings ---
            port_bindings = {}
            exposed_ports = {}
            for port in svc.get("ports", []):
                if isinstance(port, dict):
                    # New style (dict) - rare in compose, but safe
                    container_port = str(port.get("target"))
                    host_port = str(port.get("published"))
                elif isinstance(port, str):
                    if ":" in port:
                        # Long syntax: "8080:80"
                        parts = port.split(":", 1)
                        host_port, container_port = parts[0], parts[1]
                    else:
                        # Short syntax: "80" → map to random host port
                        host_port = ""  # Let Podman assign
                        container_port = port
                else:
                    # If port is an integer (e.g., 80)
                    container_port = str(port)
                    host_port = ""

                # Ensure container_port is valid
                if not container_port:
                    continue

                port_key = f"{container_port}/tcp"
                exposed_ports[port_key] = {}
                if port_key not in port_bindings:
                    port_bindings[port_key] = []
                port_bindings[port_key].append({"HostPort": host_port})

            # --- Healthcheck ---
            healthcheck = svc.get("healthcheck", {})
            hc_config = {}
            if healthcheck:
                def parse_duration(d):
                    if isinstance(d, int): return d * 1_000_000_000
                    match = re.match(r'^(\d+)([a-z]+)?$', d.strip())
                    if not match: raise ValueError(f"Invalid duration: {d}")
                    val, unit = match.groups()
                    unit = unit or 's'
                    units = {'ns':1,'us':1e3,'ms':1e6,'s':1e9,'m':60e9,'h':3600e9}
                    return int(float(val) * units.get(unit, 1))
                
                hc_config = {
                    "Test": healthcheck.get("test", ["CMD-SHELL", "exit 1"]),
                    "Interval": parse_duration(healthcheck.get("interval", "30s")),
                    "Timeout": parse_duration(healthcheck.get("timeout", "30s")),
                    "Retries": healthcheck.get("retries", 3),
                    "StartPeriod": parse_duration(healthcheck.get("start_period", "0s"))
                }

            # --- Networks ---
            network_names = []
            if "networks" in svc:
                if isinstance(svc["networks"], list):
                    network_names = svc["networks"]
                elif isinstance(svc["networks"], dict):
                    network_names = list(svc["networks"].keys())
            endpoint_config = {name: {} for name in network_names}

            # --- Volumes ---
            binds = []
            for vol in svc.get("volumes", []):
                if isinstance(vol, str):
                    if ":" in vol:
                        parts = vol.split(":")
                        if len(parts) >= 2:
                            host_path = parts[0]
                            container_path = parts[1]
                            mode = parts[2] if len(parts) > 2 else "rw"
                            binds.append(f"{host_path}:{container_path}:{mode},Z")

            # --- Container Config ---
            container_config = {
                "Image": image,
                "ExposedPorts": exposed_ports,
                "Healthcheck": hc_config,
                "HostConfig": {
                    "PortBindings": port_bindings,
                    "Binds": binds,
                },
                "NetworkingConfig": {
                    "EndpointsConfig": endpoint_config
                }
            }

            # Container name
            container_name = svc.get("container_name", service_name)

            # Create container
            create_resp = api_post(f"/containers/create?name={container_name}", json=container_config)
            if create_resp and create_resp.status_code == 201:
                container_id = create_resp.json().get("Id")
                logger.info(f"Container '{container_name}' created: {container_id[:12]}")

                # Start container
                start_resp = api_post(f"/containers/{container_id}/start")
                if start_resp and start_resp.status_code == 204:
                    logger.info(f"Container '{container_name}' started")
                else:
                    logger.error(f"Failed to start '{container_name}': {start_resp.text if start_resp else 'No response'}")
            else:
                logger.error(f"Failed to create '{container_name}': {create_resp.text if create_resp else 'No response'}")

        return redirect(url_for("index"))

    else:
        # GET: Show compose form
        return render_template("compose_deploy.html")


# 🌐 Network Actions
@app.route("/networks/create", methods=["POST"])
def create_network():
    name = request.form.get("name", "").strip()
    driver = request.form.get("driver", "bridge").strip()
    if not name:
        logger.warning("Create network: no name provided")
        return redirect(url_for("index"))

    logger.info(f"Creating network: {name} ({driver})")
    resp = api_post("/networks/create", json={"Name": name, "Driver": driver})
    if resp and resp.status_code == 201:
        logger.info(f"Network {name} created")
    else:
        logger.error(f"Failed to create network {name}")
    return redirect(url_for("index"))


@app.route("/networks/remove/<net_name>")
def remove_network(net_name):
    logger.info(f"Removing network {net_name}")
    resp = api_delete(f"/networks/{net_name}")
    if resp and resp.status_code in [200, 204]:
        logger.info(f"Network {net_name} removed")
    else:
        logger.error(f"Failed to remove network {net_name}")
    return redirect(url_for("index"))


# ➕ Container Create Form
@app.route("/containers/create", methods=["GET", "POST"])
def create_container():
    if request.method == "POST":
        name = request.form.get("name")
        image = request.form.get("image")
        command = request.form.get("command", "").strip()
        ports = request.form.get("ports", "").strip()
        selected_network = request.form.get("network", "bridge")  # Single network

        # Parse volumes: volume_name → container_path
        volume_names = request.form.getlist("volume_name")
        volume_paths = request.form.getlist("volume_path")
        binds = []
        for vol_name, vol_path in zip(volume_names, volume_paths):
            if vol_name and vol_path:
                binds.append(f"{vol_name}:{vol_path}:Z")  # :Z for SELinux

        # Parse ports
        port_bindings = {}
        if ports:
            for p in [item.strip() for item in ports.split(",") if item.strip()]:
                if ":" in p:
                    host, container = p.split(":", 1)
                else:
                    host = container = p
                port_key = f"{container}/tcp"
                if port_key not in port_bindings:
                    port_bindings[port_key] = []
                port_bindings[port_key].append({"HostPort": host})

        # ✅ Parse environment variables
        env_vars = []
        env_keys = request.form.getlist("env_key")
        env_values = request.form.getlist("env_value")
        for k, v in zip(env_keys, env_values):
            if k.strip():
                env_vars.append(f"{k.strip()}={v.strip()}")

        # ✅ Parse restart policy
        restart_policy = request.form.get("restart_policy", "no")
        restart_config = {}
        if restart_policy == "always":
            restart_config = {"Name": "always"}
        elif restart_policy == "unless-stopped":
            restart_config = {"Name": "unless-stopped"}
        elif restart_policy == "on-failure":
            restart_config = {"Name": "on-failure", "MaximumRetryCount": 5}

        # Build config
        config = {
            "Image": image,
            "Name": name,
            "Env": env_vars,  # ✅ Add environment variables
            "HostConfig": {
                "PortBindings": port_bindings,
                "Binds": binds,
                "NetworkMode": selected_network  # Critical: set network at create time
            },
        }

        # ✅ Add restart policy if set
        if restart_config:
            config["HostConfig"]["RestartPolicy"] = restart_config

        if command:
            config["Cmd"] = command.split()

        logger.info(f"Creating container with config: {config}")

        # Create container
        response = api_post("/containers/create", json=config)
        if response and response.status_code == 201:
            logger.info(f"Container {name} created successfully")
            return redirect(url_for("index"))
        else:
            error_msg = response.text if response else "No response"
            logger.error(f"Failed to create container {name}: {error_msg}")
            return f"<script>alert('Create failed: {error_msg[:200]}'); history.back();</script>"

    else:
        # GET: Show form
        images = api_get("/images/json")
        raw_volumes = api_get("/volumes")
        raw_networks = api_get("/networks")

        # ✅ Robust volume parsing
        volumes = []
        if isinstance(raw_volumes, dict) and "Volumes" in raw_volumes:
            volumes = [v["Name"] for v in raw_volumes["Volumes"] if isinstance(v, dict) and "Name" in v]

        # ✅ Robust network parsing (handles single dict or list)
        networks = []
        if isinstance(raw_networks, list):
            networks = [n["Name"] for n in raw_networks if isinstance(n, dict) and "Name" in n]
        elif isinstance(raw_networks, dict):
            if "Name" in raw_networks:
                networks = [raw_networks["Name"]]

        logger.info(f"Populating form: {len(images)} images, {len(volumes)} volumes, {len(networks)} networks")

        return render_template("create_container.html",
                               images=images,
                               volumes=volumes,
                               networks=networks)

@app.template_filter('timestamp')
def format_timestamp(ts):
    """Convert Unix timestamp to readable format"""
    dt = datetime.fromtimestamp(ts / 1000)  # Podman uses milliseconds
    return dt.strftime("%Y-%m-%d %H:%M:%S")

#file upload route
def scp_to_fc(target_path, local_path):
    """Copy file from jump server to FCOS"""
    try:
        result = subprocess.run([
            "scp", 
            "-i", "/home/innuser004/.ssh/id_coreos",  # Update path to your key
            local_path, 
            f"core@192.168.192.155:{target_path}"
        ], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info(f"File copied to FCOS: {target_path}")
            return True, result.stdout
        else:
            logger.error(f"SCP failed: {result.stderr}")
            return False, result.stderr
    except Exception as e:
        logger.error(f"SCP error: {str(e)}")
        return False, str(e)


@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return "<script>alert('No file selected'); history.back();</script>"
    
    file = request.files['file']
    target_path = request.form.get("target_path", "").strip()
    
    if not file.filename or not target_path:
        return "<script>alert('File or path missing'); history.back();</script>"
    
    # ✅ Use original filename
    filename = secure_filename(file.filename)
    
    # If target_path ends with '/', treat it as directory
    if target_path.endswith("/"):
        remote_path = target_path + filename
    else:
        # Assume target_path includes filename or is a directory
        if "/" in target_path:
            remote_path = target_path
        else:
            remote_path = f"{target_path}/{filename}"
    
    # Save with original name
    with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name
    
    try:
        # Copy to FCOS
        success, msg = scp_to_fc(remote_path, tmp_path)
        if success:
            logger.info(f"Uploaded {filename} to FCOS: {remote_path}")
            return f"<script>alert('File uploaded successfully: {filename}'); history.back();</script>"
        else:
            return f"<script>alert('Upload failed: {msg[:100]}'); history.back();</script>"
    finally:
        os.unlink(tmp_path)  # Clean up temp file


# @app.route("/images/search")
# def search_images():
#     query = request.args.get("q", "").strip()
#     print(f"🔍 /images/search called with q={query}")  # Debug
#     if not query:
#         return {"results": []}

#     try:
#         url = f"https://hub.docker.com/v2/repositories/library/{query}/"
#         print(f"📡 GET {url}")  # Debug
#         response = requests.get(url, timeout=5)
#         print(f"📥 Status: {response.status_code}, Body: {response.text[:200]}")  # Debug

#         if response.status_code == 200:
#             data = response.json()
#             return {
#                 "results": [{
#                     "name": data["name"],
#                     "namespace": data["namespace"],
#                     "title": data.get("title", ""),
#                     "description": data.get("description", "No description"),
#                     "pull_count": data.get("pull_count", 0),
#                     "star_count": data.get("star_count", 0),
#                     "is_official": data.get("is_official", False)
#                 }]
#             }

#         # Try public repo
#         url = f"https://hub.docker.com/v2/repositories/{query}/"
#         print(f"📡 GET {url}")  # Debug
#         response = requests.get(url, timeout=5)
#         print(f"📥 Status: {response.status_code}, Body: {response.text[:200]}")  # Debug

#         if response.status_code == 200:
#             data = response.json()
#             return {
#                 "results": [{
#                     "name": data["name"],
#                     "namespace": data["namespace"],
#                     "title": data.get("title", ""),
#                     "description": data.get("description", "No description"),
#                     "pull_count": data.get("pull_count", 0),
#                     "star_count": data.get("star_count", 0),
#                     "is_official": data.get("is_official", False)
#                 }]
#             }

#         return {"results": []}
#     except Exception as e:
#         print(f"❌ Search failed: {str(e)}")
#         import traceback
#         traceback.print_exc()
#         return {"results": []}


@app.route("/api/docker-hub/search")
def search_docker_hub():
    query = request.args.get("q", "").strip()
    if not query:
        return {"results": []}

    try:
        # Fetch search results from Docker Hub
        url = f"https://hub.docker.com/v2/repositories/library/{query}/"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                "results": [
                    {
                        "name": data["name"],
                        "namespace": data["namespace"],
                        "description": data["description"],
                        "pull_count": data.get("pull_count", 0),
                        "latest_tag": data.get("tag_latest", {}).get("name", "Unknown"),
                        "size": data.get("full_size", 0),
                    }
                ]
            }

        # Fallback to public repositories
        url = f"https://hub.docker.com/v2/repositories/{query}/"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                "results": [
                    {
                        "name": data["name"],
                        "namespace": data["namespace"],
                        "description": data["description"],
                        "pull_count": data.get("pull_count", 0),
                        "latest_tag": data.get("tag_latest", {}).get("name", "Unknown"),
                        "size": data.get("full_size", 0),
                    }
                ]
            }

        return {"results": []}
    except Exception as e:
        logger.error(f"Error searching Docker Hub: {str(e)}")
        return {"results": []}
    


@app.route("/api/docker-hub/repo/<image>")
def proxy_repo_info(image):
    try:
        # Try official library first
        url = f"https://hub.docker.com/v2/repositories/library/{image}/"
        response = requests.get(url, timeout=5)
        
        if response.status_code != 200:
            # Try public repo
            url = f"https://hub.docker.com/v2/repositories/{image}/"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                return {"found": False}

        data = response.json()
        
        return {
            "found": True,
            "name": data["name"],
            "namespace": data["namespace"],
            "description": data.get("description", ""),
            "full_description": parse_dockerhub_markdown(data.get("full_description", "")),
            "pull_count": data.get("pull_count", 0),
            "star_count": data.get("star_count", 0),
            "is_official": data.get("is_official", False) or data["namespace"] == "library",
            "last_updated": data.get("last_updated"),
            "categories": data.get("categories", []),
            "storage_size": data.get("storage_size", 0)
        }
    except Exception as e:
        return {"found": False, "error": str(e)}

@app.route("/api/docker-hub/tag/<image>/<tag>")
def proxy_tag_info(image, tag):
    try:
        url = f"https://hub.docker.com/v2/repositories/library/{image}/tags/{tag}/"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            url = f"https://hub.docker.com/v2/repositories/{image}/tags/{tag}/"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                return {}

        data = response.json()
        return {
            "name": data.get("name"),
            "full_size": data.get("full_size"),
            "last_updated": data.get("last_updated"),
            "images": data.get("images", [])
        }
    except Exception as e:
        return {}

def parse_dockerhub_markdown(md):
    import re
    sections = {}
    current = None
    lines = md.split("\n")
    
    for line in lines:
        match = re.match(r"^# (.+)$", line)
        if match:
            current = match.group(1).strip()
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line.strip())
    
    return sections



if __name__ == "__main__":
    logger.info("Starting Flask app on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)