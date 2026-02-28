# Kubernetes Migration Guide for OSINT Nexus

To test the Kubernetes cluster locally on your WSL Ubuntu environment:

1. **Install and Start Minikube (with GPU)**
```bash
minikube start --driver=docker --gpus all --memory=8192
```

2. **Load the Docker Images into Minikube**
Since K8s doesn't read your host machine's docker cache by default:
```bash
minikube image load osint-backend:latest
minikube image load osint-frontend:latest
```

3. **Deploy the Manifests**
```bash
kubectl apply -f k8s/
```

4. **Verify and Monitor**
```bash
kubectl get pods -n osint -w
```
Wait for all pods to show `Running`.

5. **Access the Dashboard**
Find the Minikube IP:
```bash
minikube ip
```
Open your browser and navigate to `http://<MINIKUBE_IP>:30000`
