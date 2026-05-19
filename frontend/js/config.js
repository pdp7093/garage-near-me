function getApiBase() {
    const host = window.location.hostname;

    // Local development
    if (
        host === "localhost" ||
        host === "127.0.0.1"
    ) {
        return "http://localhost:8000/api";
    }

    // Ngrok / production
    return "https://YOUR_BACKEND_NGROK.ngrok-free.app/api";
}