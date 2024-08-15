import time, sys, random
import argparse
import subprocess
import subprocess
import threading

from kubernetes import client, config
from tabulate import tabulate
import colorama
from colorama import Fore, Back, Style

colorama.init(autoreset=True)

parser = argparse.ArgumentParser(description='TBD')
parser.add_argument('--drone_count', type=int, default=15, help='Specify number of drones in simulation')
parser.add_argument('--startup', action='store_true', help='Complete initial startup process (minikube)')
parser.add_argument('--tesla_disclosure_time', type=int, default=10, help='Disclosure period in seconds of every TESLA key disclosure message')
parser.add_argument('--max_hop_count', type=int, default=8, help='Maximium number of nodes we can route messages through')
args = parser.parse_args()

droneNum = args.drone_count
droneImage = "cyu72/drone:latest"
gcsImage = "cyu72/gcs:latest"

if args.startup:
  subprocess.run("minikube start --insecure-registry='localhost:5001' --network-plugin=cni --cni=calico", shell=True, check=True)
  subprocess.run("kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.4/manifests/calico.yaml", shell=True, check=True)
  subprocess.run("kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.13.12/config/manifests/metallb-native.yaml", shell=True, check=True)
  subprocess.run("minikube addons enable metallb", shell=True, check=True)

delim = "---\n"

with open('etc/kubernetes/droneDeployment.yml', 'w') as file: 
    nodePort = 30001
    for num in range(1, droneNum + 1):
        drone = f"""apiVersion: v1
kind: Pod
metadata:
  name: drone{num}
  namespace: default
  labels:
    app: drone{num}
    tier: drone
spec:
  hostname: drone{num}
  containers: 
    - name: drone{num}
      image: {droneImage}
      env:
        - name: PARAM1
          value: "drone{num}"
        - name: PARAM2
          value: "65456"
        - name: PARAM3
          value: "{num}"
        - name: TESLA_DISCLOSE
          value: "{args.tesla_disclosure_time}"
        - name: MAX_HOP_COUNT
          value: "{args.max_hop_count}"
      ports:
        - name: action-port
          protocol: TCP
          containerPort: 65456
        - name: brdcst-port
          protocol: UDP
          containerPort: 65457
        - name: start-port
          protocol: TCP
          containerPort: 8080
"""
        service = f"""apiVersion: v1
kind: Service
metadata:
  name: drone{num}-service
spec:
  type: LoadBalancer
  selector:
    app: drone{num}
    tier: drone
  ports:
  - name: drone-port
    protocol: TCP
    port: 80
    targetPort: 65456
  - name: udp-test-port
    protocol: UDP
    port: 65457
    targetPort: 65457
  - name: start-port
    protocol: TCP
    port: 8080
    targetPort: 8080 
    nodePort: {nodePort}
"""
        file.write(drone)
        file.write(delim)
        file.write(service)
        file.write(delim)
        nodePort += 1

        
    gcs = f"""apiVersion: v1
kind: Pod
metadata:
  name: gcs
  namespace: default
  labels:
    app: gcs
    tier: drone
spec:
  hostname: gcs
  containers: 
    - name: gcs
      image: {gcsImage}
      stdin: true
      tty: true
      ports:
        - name: main-port
          protocol: TCP
          containerPort: 65456
        - name: udp-test-port
          protocol: UDP
          containerPort: 65457"""
    
    configMap = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: config
  namespace: metallb-system
data:
  config: |
    address-pools:
    - name: default
      protocol: layer2
      addresses:
      - 192.168.1.101-192.168.1.150
"""
    
    file.write(gcs + "\n" + delim + configMap + "\n")
    file.close()

# Create a matrix that is of variable size
# Randomly place each drone in the matrix, where each drone is represented by its number

matrix = []
def generate_random_matrix(n, numDrones):
  matrix = [[0] * n for _ in range(n)]
  drone_numbers = random.sample(range(1, numDrones + 1), numDrones)
  
  for num in drone_numbers:
    while True:
      row = random.randint(0, n - 1)
      col = random.randint(0, n - 1)
      if matrix[row][col] == 0:
        matrix[row][col] = num
        break
  
  return matrix

n = 8  # size of the matrix
valid_config = False

while not valid_config:
  matrix = generate_random_matrix(n, droneNum)

  for row in matrix:
    for element in row:
      print("{:2}".format(element), end=' ')
    print()

  user_input = input("Is this a valid configuration? (yes/no): ")
  if user_input.lower() == "yes":
    valid_config = True

if (args.startup):
    time.sleep(45) # Wait for calico to turn on before applying network policies

with open('etc/kubernetes/deploymentNetworkPolicy.yml', 'w') as file:
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            if matrix[i][j] != 0:
                neighbors = []
                if i > 0 and matrix[i-1][j] != 0: # Only 4 tiles around
                    neighbors.append(matrix[i-1][j])
                if i < len(matrix)-1 and matrix[i+1][j] != 0:
                    neighbors.append(matrix[i+1][j])
                if j > 0 and matrix[i][j-1] != 0:
                    neighbors.append(matrix[i][j-1])
                if j < len(matrix[i])-1 and matrix[i][j+1] != 0:
                    neighbors.append(matrix[i][j+1])

                print(f"Neighbors of drone{matrix[i][j]}: {neighbors}")
                if neighbors:
                  networkPolicy = f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ingress-selector{matrix[i][j]}
spec:
  podSelector:
    matchLabels:
      app: drone{matrix[i][j]}
      tier: drone
  ingress:
  - from:
    - podSelector:
        matchExpressions:
        - {{key: app, operator: In, values: [gcs, {', '.join(['drone' + str(neighbor) for neighbor in neighbors])}]}}"""
                  file.write(networkPolicy + "\n" + delim)
                else:
                    networkPolicy = f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ingress-selector{matrix[i][j]}
spec:
  podSelector:
    matchLabels:
      app: drone{matrix[i][j]}
      tier: drone
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: gcs"""
                    file.write(networkPolicy + "\n" + delim)

file.close()
# Generate Manifest End

# Apply Manifests
command = "kubectl apply -f etc/kubernetes/droneDeployment.yml"
process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
command = "kubectl apply -f etc/kubernetes/deploymentNetworkPolicy.yml"
process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

time.sleep(20) # Need to wait for command to execute all yaml files

processes = []

def run_command(command):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processes.append(process)
    output, error = process.communicate()
    return output.decode(), error.decode()

threads = []

while True:
    config.load_kube_config()
    api_instance = client.CoreV1Api()

    pods = api_instance.list_pod_for_all_namespaces(watch=False)
    services = api_instance.list_service_for_all_namespaces()

    all_running = True
    for pod in pods.items:
        if pod.status.phase != "Running":
            all_running = False
            time.sleep(10) # Wait for all pods to start
            break


    # Port forward all services to be accessible from outside the cluster
    if all_running:
        print("All pods are running")
        time.sleep(5)
        for service in services.items:
            if service.spec.type == "LoadBalancer" and service.metadata.name.startswith("drone"):
                drone_number = service.metadata.name.split("drone")[1].split("-")[0]
                nodePort = 30000 + int(drone_number)
                print(f"Service: {service.metadata.name}")
                command = f"kubectl port-forward svc/{service.metadata.name} {nodePort}:8080"
                
                thread = threading.Thread(target=run_command, args=(command,))
                thread.start()
                threads.append(thread)


        # Send a request to each service
        time.sleep(5)
        for service in services.items:
            if service.spec.type == "LoadBalancer" and service.metadata.name.startswith("drone"):
                drone_number = service.metadata.name.split("drone")[1].split("-")[0]
                nodePort = 30000 + int(drone_number)
                print(f"Service: {service.metadata.name}")

                for ingress in service.status.load_balancer.ingress:
                    url = f"http://127.0.0.1:{nodePort}"
                    print(f"Sending request to {url}")

                    process = subprocess.Popen(f"curl {url}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    print(process.stdout.read().decode())
        for process in processes:
            process.terminate()
        break

    else:
        print("Not all pods are running")

def print_matrix(matrix):
    # Create header row with column numbers
    headers = [''] + [str(i) for i in range(len(matrix[0]))]
    
    # Create table data with row numbers
    table_data = []
    for i, row in enumerate(matrix):
        colored_row = [str(i)]  # Row number
        for element in row:
            if element == 0:
                colored_row.append(f"{Fore.LIGHTBLACK_EX}{element:2}{Style.RESET_ALL}")
            else:
                colored_row.append(f"{Fore.GREEN}{Back.LIGHTWHITE_EX}{element:2}{Style.RESET_ALL}")
        table_data.append(colored_row)
    
    # Print the table
    print(tabulate(table_data, headers=headers, tablefmt="fancy_grid"))
    print(f"\n{Fore.CYAN}Legend: {Fore.GREEN}{Back.LIGHTWHITE_EX} Drone {Style.RESET_ALL} | {Fore.LIGHTBLACK_EX}0{Style.RESET_ALL} Empty Space")


def get_neighbors(matrix, i, j):
    neighbors = []
    if i > 0 and matrix[i-1][j] != 0:
        neighbors.append(matrix[i-1][j])
    if i < len(matrix)-1 and matrix[i+1][j] != 0:
        neighbors.append(matrix[i+1][j])
    if j > 0 and matrix[i][j-1] != 0:
        neighbors.append(matrix[i][j-1])
    if j < len(matrix[i])-1 and matrix[i][j+1] != 0:
        neighbors.append(matrix[i][j+1])
    return neighbors

def create_network_policy(drone_number, neighbors):
    return f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ingress-selector{drone_number}
spec:
  podSelector:
    matchLabels:
      app: drone{drone_number}
      tier: drone
  ingress:
  - from:
    - podSelector:
        matchExpressions:
        - {{key: app, operator: In, values: [gcs, {', '.join(['drone' + str(neighbor) for neighbor in neighbors])}]}}"""

def update_network_policies(matrix):
    policies = []
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            if matrix[i][j] != 0:
                neighbors = get_neighbors(matrix, i, j)
                policy = create_network_policy(matrix[i][j], neighbors)
                policies.append(policy)
    
    with open('etc/kubernetes/deploymentNetworkPolicy.yml', 'w') as file:
        file.write("\n---\n".join(policies))
    
    subprocess.run("kubectl apply -f etc/kubernetes/deploymentNetworkPolicy.yml", shell=True, check=True)

def move_drone(matrix, from_pos, to_pos):
    from_i, from_j = from_pos
    to_i, to_j = to_pos
    drone = matrix[from_i][from_j]
    matrix[from_i][from_j] = 0
    matrix[to_i][to_j] = drone
    return matrix

while True:
    print_matrix(matrix)
    user_input = input("Enter move (drone_number from_i from_j to_i to_j) or 'q' to quit: ")
    
    if user_input.lower() == 'q':
        break
    
    try:
        drone, from_i, from_j, to_i, to_j = map(int, user_input.split())
        if matrix[from_i][from_j] != drone:
            print(f"Error: Drone {drone} is not at position ({from_i}, {from_j})")
            continue
        if matrix[to_i][to_j] != 0:
            print(f"Error: Position ({to_i}, {to_j}) is not empty")
            continue
        
        matrix = move_drone(matrix, (from_i, from_j), (to_i, to_j))
        update_network_policies(matrix)
        print("Network policies updated.")
    except ValueError:
        print("Invalid input. Please use format: drone_number from_i from_j to_i to_j")
    except IndexError:
        print("Invalid position. Please ensure all indices are within the matrix bounds.")