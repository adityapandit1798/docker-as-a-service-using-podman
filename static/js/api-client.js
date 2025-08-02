// static/js/api-client.js
class APIClient {
    static async get(endpoint) {
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error(`GET ${endpoint}: ${response.status}`);
        return await response.json();
    }

    static async post(endpoint, data = null) {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });
        return response.ok ? await response.json().catch(() => ({})) : null;
    }

    static async delete(endpoint) {
        const response = await fetch(endpoint, { method: "DELETE" });
        return response.ok;
    }
}