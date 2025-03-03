# Simulation Startup Guide

## Quick Start

1. **First-time startup:**
   ```
   python3 run.py --startup
   ```

2. **View all available flags (optional):**
   ```
   python3 run.py --help
   ```

3. **Configure IP address:**
   - Run `ifconfig` and locate the `inet addr`
   - Use this IP address in your configuration

## Deployment Steps

1. Build Docker image, tag, and push to DockerHub
2. Start Minikube
3. Apply Kubernetes manifests

### Docker Build and Push

```bash
docker build -t cyu72/<image-name>:latest -f <path-to-dockerfile> .
docker push cyu82/repository:tag
```

## Kubernetes Commands

| Action | Command |
|--------|---------|
| Delete all pods | `kubectl delete pods --all` |
| Check pods | `kubectl get pods` |
| Describe a pod | `kubectl describe pods [pod-name]` |
| Apply Kubernetes file | `kubectl apply -f [deployment.yaml]` |
| Connect to container | `kubectl attach <container-name>` |
| Connect interactively | `kubectl attach -it <container-name>` |
| Connect to specific pod | `kubectl attach <container-name> -c <pod-name>` |

## Helpful Resources

- YAML Linter: [https://www.yamllint.com/](https://www.yamllint.com/)
- Kube by Example (MetalLB): [https://kubebyexample.com/learning-paths/metallb/install](https://kubebyexample.com/learning-paths/metallb/install)
