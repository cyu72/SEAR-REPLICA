import time, sys, random
import math
import argparse
import subprocess
import threading
import requests

from flask import Flask, request, jsonify
from kubernetes import client, config
from tabulate import tabulate
import colorama
from colorama import Fore, Back, Style
import time

app = Flask(__name__)
colorama.init(autoreset=True)
matrix = []

parser = argparse.ArgumentParser(description='TBD')
parser.add_argument('--drone_count', type=int, default=26, help='Specify number of drones in simulation')
parser.add_argument('--startup', action='store_true', help='Complete initial startup process (minikube)')
parser.add_argument('--tesla_disclosure_time', type=int, default=10, help='Disclosure period in seconds of every TESLA key disclosure message')
parser.add_argument('--max_hop_count', type=int, default=25, help='Maximium number of nodes we can route messages through')
parser.add_argument('--max_seq_count', type=int, default=50, help='Maximium number of sequence numbers we can store')
parser.add_argument('--timeout', type=int, default=30, help='Timeout for each request')
parser.add_argument('--grid_size', type=int, default=12, help='Defines nxn sized grid.')
parser.add_argument('--grid_type', choices=['random', 'hardcoded'], default='hardcoded', help='Choose between random or hardcoded grid')
parser.add_argument('--log_level', choices=['DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL', 'TRACE'], default='DEBUG', help='Set the log level for the drone')
parser.add_argument('--simulation_level', choices=['kube', 'pi'], default='kube', help='Set the simulation level')
parser.add_argument('--SKIP_VERIFICATION', choices=['True', 'False'], default='True', help='Skip verification for certification yield')
args = parser.parse_args()

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

def generate_hardcoded_matrix(n, numDrones):
    array = [
        [0, 0, 0, 0, 0, 0, 14, 15, 16, 17, 18, 0],
        [0, 0, 0, 0, 0, 0, 13, 0, 0, 0, 19, 0],
        [0, 0, 0, 0, 0, 0, 12, 0, 0, 0, 20, 0],
        [0, 0, 0, 0, 0, 0, 11, 0, 0, 0, 21, 0],
        [0, 0, 0, 0, 0, 0, 10, 0, 0, 0, 22, 0],
        [0, 0, 0, 0, 0, 0, 9, 0, 0, 0, 23, 0],
        [3, 4, 1, 2, 6, 7, 8, 0, 0, 0, 24, 0],
        [5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 25, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 26, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    ]
    
    return array

def run_command(command):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    processes.append(process)
    output, error = process.communicate()
    return output.decode(), error.decode()

def partition_grid(matrix, leader_drones):
    n = len(matrix)
    partitions = []
    used_cells = set()
    
    # Sort leaders from top to bottom, then left to right
    leader_drones.sort(key=lambda x: (x[1], x[2]))
    
    for leader_id, leader_row, leader_col in leader_drones:
        # If this leader's position is already in another partition, skip it
        if (leader_row, leader_col) in used_cells:
            continue
            
        # Initialize partition boundaries
        start_row = leader_row
        end_row = leader_row
        start_col = leader_col
        end_col = leader_col
        
        # Find closest leader above and below
        above_row = -1
        below_row = n
        left_col = -1
        right_col = n
        
        for other_id, other_row, other_col in leader_drones:
            if other_id != leader_id:
                # Find vertical boundaries
                if other_row < leader_row and other_row > above_row:
                    above_row = other_row
                elif other_row > leader_row and other_row < below_row:
                    below_row = other_row
                    
                # Find horizontal boundaries
                if other_col < leader_col and other_col > left_col:
                    left_col = other_col
                elif other_col > leader_col and other_col < right_col:
                    right_col = other_col
        
        # Calculate partition boundaries
        if above_row != -1:
            start_row = (above_row + leader_row) // 2
        else:
            start_row = 0
            
        if below_row != n:
            end_row = (below_row + leader_row) // 2
        else:
            end_row = n - 1
            
        if left_col != -1:
            start_col = (left_col + leader_col) // 2
        else:
            start_col = 0
            
        if right_col != n:
            end_col = (right_col + leader_col) // 2
        else:
            end_col = n - 1
        
        # Mark all cells in this partition as used
        for i in range(start_row, end_row + 1):
            for j in range(start_col, end_col + 1):
                used_cells.add((i, j))
        
        # Create partition with all drones in the boundary
        partition = {
            "leader": leader_id,
            "start_row": start_row,
            "end_row": end_row,
            "start_col": start_col,
            "end_col": end_col,
            "drones": []
        }
        
        # Find all drones within the partition boundaries
        for i in range(start_row, end_row + 1):
            for j in range(start_col, end_col + 1):
                if matrix[i][j] != 0:
                    partition["drones"].append((matrix[i][j], i, j))
        
        partitions.append(partition)
    
    # Handle any unassigned cells by expanding existing partitions
    unassigned = []
    for i in range(n):
        for j in range(n):
            if (i, j) not in used_cells:
                unassigned.append((i, j))
    
    if unassigned:
        # Assign unassigned cells to the nearest partition
        for i, j in unassigned:
            min_distance = float('inf')
            closest_partition = None
            
            for partition in partitions:
                # Calculate distance to partition center
                center_row = (partition["start_row"] + partition["end_row"]) / 2
                center_col = (partition["start_col"] + partition["end_col"]) / 2
                distance = ((i - center_row) ** 2 + (j - center_col) ** 2) ** 0.5
                
                if distance < min_distance:
                    min_distance = distance
                    closest_partition = partition
            
            if closest_partition:
                # Expand the closest partition to include this cell
                closest_partition["start_row"] = min(closest_partition["start_row"], i)
                closest_partition["end_row"] = max(closest_partition["end_row"], i)
                closest_partition["start_col"] = min(closest_partition["start_col"], j)
                closest_partition["end_col"] = max(closest_partition["end_col"], j)
                
                # Add any drones in this cell to the partition
                if matrix[i][j] != 0:
                    closest_partition["drones"].append((matrix[i][j], i, j))
    
    print(f"Partitions: {partitions}")
    return partitions

def select_leader_drones(matrix, num_leaders):
    if args.grid_type == 'random':
        drones = [(matrix[i][j], i, j) for i in range(len(matrix)) for j in range(len(matrix[i])) if matrix[i][j] != 0]
        return random.sample(drones, min(num_leaders, len(drones)))
    else:
        hardcoded_leaders = [(1, 0, 0), (5, 4, 0), (11, 9, 0)]
        return hardcoded_leaders[:num_leaders]

def print_matrix(matrix):
    headers = [''] + [str(i) for i in range(len(matrix[0]))]
    
    table_data = []
    for i, row in enumerate(matrix):
        colored_row = [str(i)]
        for element in row:
            if element == 0:
                colored_row.append(f"{Fore.LIGHTBLACK_EX}{element:2}{Style.RESET_ALL}")
            else:
                colored_row.append(f"{Fore.GREEN}{Back.LIGHTWHITE_EX}{element:2}{Style.RESET_ALL}")
        table_data.append(colored_row)
    
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

def create_network_policies(matrix):
    policies = []
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            if matrix[i][j] != 0:
                neighbors = get_neighbors(matrix, i, j)
                policy = f"""apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ingress-selector{matrix[i][j]}
spec:
  podSelector:
    matchLabels:
      app: drone{matrix[i][j]}
      tier: drone
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: gcs
    ports:
    - protocol: TCP
      port: 65456
    - protocol: UDP
      port: 65457
    - protocol: TCP
      port: 8080
    - protocol: TCP
      port: 60137
  - from:
    - podSelector:
        matchExpressions:
        - key: app
          operator: In
          values: [{', '.join([f'drone{n}' for n in neighbors])}]
    ports:
    - protocol: TCP
      port: 65456
    - protocol: UDP
      port: 65457
    - protocol: TCP
      port: 8080
    - protocol: TCP
      port: 60137"""
                policies.append(policy)
    
    with open('etc/kubernetes/deploymentNetworkPolicy.yml', 'w') as file:
        file.write("\n---\n".join(policies))
    
    subprocess.run("kubectl apply -f etc/kubernetes/deploymentNetworkPolicy.yml", shell=True, check=True)

def move_drone(matrix, drone, to_pos):
    to_i, to_j = to_pos
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            if matrix[i][j] == drone:
                matrix[i][j] = 0
                matrix[to_i][to_j] = drone
                return matrix
    raise ValueError(f"Drone {drone} not found in the matrix")

@app.route('/coords', methods=['GET'])
def get_coords():
    return jsonify({"matrix": matrix}), 200

@app.route('/update_coords', methods=['POST'])
def update_coords():
    global matrix
    message = request.json
    try:
        drone = int(message['drone-id'])
        to_i = int(float(message['x']))
        to_j = int(float(message['y']))
        
        if to_i < 0 or to_i >= len(matrix) or to_j < 0 or to_j >= len(matrix[0]):
            return jsonify({"error": f"Position ({to_i}, {to_j}) is out of bounds"}), 400
        
        current_pos = None
        for i in range(len(matrix)):
            for j in range(len(matrix[0])):
                if matrix[i][j] == drone:
                    current_pos = (i, j)
                    break
            if current_pos:
                break
        
        if current_pos and current_pos == (to_i, to_j):
            print_matrix(matrix)
            return jsonify({
                "message": "Drone is already at the requested position",
                "new_matrix": matrix
            }), 200
        
        if matrix[to_i][to_j] != 0:
            return jsonify({"error": f"Position ({to_i}, {to_j}) is not empty"}), 400
        
        matrix = move_drone(matrix, drone, (to_i, to_j))
        create_network_policies(matrix)
        print(f"Drone {drone} moved to position ({to_i}, {to_j})")
        print("Matrix updated and network policies updated.")
        print_matrix(matrix)
        return jsonify({"message": "Coordinates updated successfully", "new_matrix": matrix}), 200
    except KeyError as e:
        return jsonify({"error": f"Invalid request format. Missing key: {str(e)}"}), 400
    except ValueError as e:
        return jsonify({"error": f"Invalid value: {str(e)}. Please provide valid integer values."}), 400
    except IndexError:
        return jsonify({"error": "Invalid position. Please ensure all indices are within the matrix bounds."}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

def run_flask_server():
    app.run(host='0.0.0.0', port=8080)

def setup_port_forwarding(services):
    for service in services.items:
        if service.spec.type == "LoadBalancer" and service.metadata.name.startswith("drone"):
            drone_number = int(service.metadata.name.split("drone")[1].split("-")[0])
            nodePort = 30000 + drone_number
            command = f"kubectl port-forward svc/{service.metadata.name} {nodePort}:8080"
            thread = threading.Thread(target=run_command, args=(command,))
            thread.start()
            threads.append(thread)
    
    time.sleep(5)

def main():
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.start()
    global matrix, processes, threads

    droneNum = args.drone_count
    droneImage = "cyu72/sear:simulation-terminal"

    controller_addr = input("Enter the controller address: ")

    if args.simulation_level == 'kube':
        gcs_ip = 'gcs-service.default'

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
    - name: logs
      image: {droneImage}
      imagePullPolicy: Always
      stdin: true
      tty: true
      env:
        - name: NODE_ID
          value: "{num}"
        - name: PORT
          value: "65456"
        - name: TESLA_DISCLOSE
          value: "{args.tesla_disclosure_time}"
        - name: MAX_HOP_COUNT
          value: "{args.max_hop_count}"
        - name: MAX_SEQ_COUNT
          value: "{args.max_seq_count}"
        - name: CONTROLLER_ADDR
          value: "{controller_addr}"
        - name: TIMEOUT_SEC
          value: "{args.timeout}"
        - name: LOG_LEVEL
          value: "{args.log_level}"
        - name: GCS_IP
          value: "{gcs_ip}"
        - name: DRONE_COUNT
          value: "{args.drone_count}"
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
        - name: ipc
          protocol: TCP
          containerPort: 60137

    - name: terminal
      image: cyu72/drone:latest
      imagePullPolicy: Always
      command: ["./drone_app", "--terminal"]
      stdin: true
      tty: true
      env:
        - name: ROUTING_HOST
          value: "localhost"
        - name: NODE_ID
          value: "{num}"
"""
            service = f"""apiVersion: v1
kind: Service
metadata:
  name: drone{num}-service
spec:
  externalTrafficPolicy: Local
  type: LoadBalancer
  selector:
    app: drone{num}
    tier: drone
  ports:
  - name: drone-port
    protocol: TCP
    port: 65456
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
        
        file.write(configMap + "\n")
        file.close()
        
    valid_config = False

    while not valid_config:
        if args.grid_type == 'random':
            matrix = generate_random_matrix(args.grid_size, droneNum)
        else:
            matrix = generate_hardcoded_matrix(args.grid_size, droneNum)

        for row in matrix:
            for element in row:
                print("{:2}".format(element), end=' ')
            print()

        user_input = input("Is this a valid configuration? (yes/no): ")
        if user_input.lower() == "yes":
            valid_config = True
            create_network_policies(matrix)

    if (args.startup):
        time.sleep(45)

    command = "kubectl apply -f etc/kubernetes/droneDeployment.yml"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    command = "kubectl apply -f etc/kubernetes/deploymentNetworkPolicy.yml"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    time.sleep(20)

    processes = []
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
                time.sleep(10)
                break

        if all_running:
            print("All pods are running")
            time.sleep(5)
            setup_port_forwarding(services)

            num_leaders = 3
            leader_drones = select_leader_drones(matrix, num_leaders)
            partitions = partition_grid(matrix, leader_drones)

            for service in services.items:
                if service.spec.type == "LoadBalancer" and service.metadata.name.startswith("drone"):
                    drone_number = int(service.metadata.name.split("drone")[1].split("-")[0])
                    nodePort = 30000 + drone_number
                    print(f"Service: {service.metadata.name}")

                    for ingress in service.status.load_balancer.ingress:
                        url = f"http://127.0.0.1:{nodePort}"
                        print(f"Sending request to {url}")

                        is_leader = any(drone[0] == drone_number for drone in leader_drones)
                        data = {"is_leader": is_leader}

                        if is_leader:
                            leader_index = next(i for i, drone in enumerate(leader_drones) if drone[0] == drone_number)
                            partition = partitions[leader_index]
                            data["partition"] = {
                                "start_row": partition["start_row"],
                                "end_row": partition["end_row"],
                                "start_col": partition["start_col"],
                                "end_col": partition["end_col"]
                            }

                        try:
                            response = requests.post(url, json=data)
                            response.raise_for_status()
                            print(f"Sent {'leader' if is_leader else 'follower'} info to Drone {drone_number}")
                        except requests.exceptions.RequestException as e:
                            print(f"Failed to send info to Drone {drone_number}: {e}")
            for process in processes:
                process.terminate()
            break

        else:
            print("Not all pods are running")

    setup_port_forwarding(services)
    while True:
        print_matrix(matrix)
        user_input = input("Enter move (drone_number to_i to_j) or 'q' to quit: ")
        
        if user_input.lower() == 'q':
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')
            func()
            flask_thread.join()
            break
        
        try:
            drone, to_i, to_j = map(int, user_input.split())
            if matrix[to_i][to_j] != 0:
                print(f"Error: Position ({to_i}, {to_j}) is not empty")
                continue
            
            matrix = move_drone(matrix, drone, (to_i, to_j))
            create_network_policies(matrix)
            print("Network policies updated.")
        except ValueError as e:
            print(f"Error: {str(e)}")
        except IndexError:
            print("Invalid position. Please ensure all indices are within the matrix bounds.")
        
        for service in services.items:
            if service.spec.type == "LoadBalancer" and service.metadata.name.startswith("drone"):
                drone_number = int(service.metadata.name.split("drone")[1].split("-")[0])
                nodePort = 30000 + drone_number
                print(f"Service: {service.metadata.name}")

                for ingress in service.status.load_balancer.ingress:
                    url = f"http://127.0.0.1:{nodePort}"
                    print(f"Sending request to {url}")

                    try:
                        response = requests.get(url)
                        response.raise_for_status()
                    except requests.exceptions.RequestException as e:
                        print(f"Failed to send info to Drone {drone_number}: {e}")
        

if __name__ == "__main__":
    main()