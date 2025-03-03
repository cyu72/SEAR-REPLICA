#ifndef TCP_SOCKET_HPP
#define TCP_SOCKET_HPP

#include <string>
#include <cstring>
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#include <netdb.h>
#include <stdexcept>
#include <vector>
#include <fcntl.h>
#include <iostream>

class TCPInterface {
public:
    TCPInterface(int port, bool is_server = true) : is_server(is_server) {
        if ((sock = socket(AF_INET, SOCK_STREAM, 0)) < 0) {
            throw std::runtime_error("TCP socket creation failed");
        }

        if (is_server) {
            memset(&server_addr, 0, sizeof(server_addr));
            server_addr.sin_family = AF_INET;
            server_addr.sin_addr.s_addr = INADDR_ANY;
            server_addr.sin_port = htons(port);

            if (bind(sock, (const struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
                close(sock);
                throw std::runtime_error("TCP bind failed");
            }

            if (listen(sock, 5) < 0) {
                close(sock);
                throw std::runtime_error("TCP listen failed");
            }
        }
    }

    ~TCPInterface() {
        close(sock);
    }

    int accept_connection() {
        if (!is_server) {
            return -1; // Failure: Cannot accept connections on a client socket
        }

        struct sockaddr_in client_addr;
        socklen_t addr_len = sizeof(client_addr);
        int client_sock = accept(sock, (struct sockaddr *)&client_addr, &addr_len);

        if (client_sock < 0) {
            return -1; // Failure: TCP accept failed
        }

        print_peer_address(client_sock);

        return client_sock; // Success: Return the client socket descriptor
    }

    int connect_to(const std::string& host, int port, int timeout_sec = 10) {
        if (is_server) {
            // std::cout << "DEBUG: Cannot connect using a server socket" << std::endl;
            return -1; // Failure: Cannot connect using a server socket
        }

        struct addrinfo hints, *result;
        memset(&hints, 0, sizeof(hints));
        hints.ai_family = AF_INET;
        hints.ai_socktype = SOCK_STREAM;

        // std::cout << "DEBUG: Attempting to resolve host: " << host << " on port: " << port << std::endl;

        int status = getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &result);
        if (status != 0) {
            std::cout << "DEBUG: Error resolving host: " << gai_strerror(status) << std::endl;
            return -1; // Failure: Error resolving host
        }

        // std::cout << "DEBUG: Host resolved successfully, attempting to connect" << std::endl;

        // Set socket to non-blocking mode
        int flags = fcntl(sock, F_GETFL, 0);
        fcntl(sock, F_SETFL, flags | O_NONBLOCK);

        int res = connect(sock, result->ai_addr, result->ai_addrlen);
        if (res < 0) {
            if (errno == EINPROGRESS) {
                struct timeval tv;
                tv.tv_sec = timeout_sec;
                tv.tv_usec = 0;

                fd_set fdset;
                FD_ZERO(&fdset);
                FD_SET(sock, &fdset);

                // Wait for the socket to become ready
                res = select(sock + 1, NULL, &fdset, NULL, &tv);
                if (res == 0) {
                    // std::cout << "DEBUG: Connection attempt timed out" << std::endl;
                    freeaddrinfo(result);
                    return -2; // Failure: Connection timeout
                } else if (res < 0) {
                    // std::cout << "DEBUG: Error in select(): " << strerror(errno) << std::endl;
                    freeaddrinfo(result);
                    return -1; // Failure: Select error
                } else {
                    // Check if the socket is actually connected
                    int error;
                    socklen_t len = sizeof(error);
                    if (getsockopt(sock, SOL_SOCKET, SO_ERROR, &error, &len) < 0 || error != 0) {
                        // std::cout << "DEBUG: Connection failed after select: " << strerror(error) << std::endl;
                        freeaddrinfo(result);
                        return -1; // Failure: Connection error
                    }
                }
            } else {
                // std::cout << "DEBUG: TCP connection failed: " << strerror(errno) << std::endl;
                freeaddrinfo(result);
                return -1; // Failure: Immediate connection error
            }
        }

        // Set socket back to blocking mode
        fcntl(sock, F_SETFL, flags);

        freeaddrinfo(result);
        // std::cout << "DEBUG: Connection established successfully" << std::endl;
        return 0; // Success
    }

    int send_data(const std::string& msg, int client_sock = -1, int timeout_sec = 5) {
        int target_sock = (client_sock == -1) ? sock : client_sock;

        // std::cout << "DEBUG: Preparing to send data to socket " << target_sock << std::endl;

        // Set send timeout
        struct timeval tv;
        tv.tv_sec = timeout_sec;
        tv.tv_usec = 0;
        if (setsockopt(target_sock, SOL_SOCKET, SO_SNDTIMEO, (const char*)&tv, sizeof tv) < 0) {
            // std::cout << "DEBUG: Error setting send timeout: " << strerror(errno) << std::endl;
            return -1; // Failure: Error setting send timeout
        }

        // std::cout << "DEBUG: Send timeout set to " << timeout_sec << " seconds" << std::endl;

        ssize_t bytes_sent = send(target_sock, msg.c_str(), msg.size(), 0);
        if (bytes_sent < 0) {
            if (errno == EWOULDBLOCK || errno == EAGAIN) {
                // std::cout << "DEBUG: Send timeout occurred" << std::endl;
                return -1; // Failure: Send timeout occurred
            } else {
                // std::cout << "DEBUG: Error sending data: " << strerror(errno) << std::endl;
                return -1; // Failure: Error sending data
            }
        }

        // std::cout << "DEBUG: Successfully sent " << bytes_sent << " bytes" << std::endl;
        return bytes_sent;
    }

    std::string receive_data(int client_sock = -1, size_t buffer_size = 1024) {
        int target_sock = (client_sock == -1) ? sock : client_sock;
        std::vector<char> buffer(buffer_size);
        ssize_t bytes_received = recv(target_sock, buffer.data(), buffer.size(), 0);

        if (bytes_received < 0) {
            throw std::runtime_error("Error receiving data: " + std::string(strerror(errno)));
        } else if (bytes_received == 0) {
            throw std::runtime_error("Connection closed by peer");
        }

        print_peer_address(target_sock);

        return std::string(buffer.data(), bytes_received);
    }

    int set_non_blocking(bool non_blocking) {
        int flags = fcntl(sock, F_GETFL, 0);
        if (flags == -1) {
            return -1; // Failure: Error getting socket flags
        }

        if (non_blocking) {
            flags |= O_NONBLOCK;
        } else {
            flags &= ~O_NONBLOCK;
        }

        if (fcntl(sock, F_SETFL, flags) == -1) {
            return -1; // Failure: Error setting socket flags
        }

        return 0; // Success
    }

private:
    int sock;
    struct sockaddr_in server_addr;
    bool is_server;

    void print_peer_address(int client_sock) {
        struct sockaddr_in addr;
        socklen_t addr_len = sizeof(addr);

        if (getpeername(client_sock, (struct sockaddr*)&addr, &addr_len) == -1) {
            std::cerr << "Error getting peer name: " << strerror(errno) << std::endl;
            return;
        }

        char ip[INET_ADDRSTRLEN];
        if (inet_ntop(AF_INET, &(addr.sin_addr), ip, INET_ADDRSTRLEN) == nullptr) {
            std::cerr << "Error converting IP to string: " << strerror(errno) << std::endl;
            return;
        }
    }
};

#endif