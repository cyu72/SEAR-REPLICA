#pragma once
#include <iostream>
#include <tuple>
#include <chrono>
#include <queue>
#include "messages.hpp"

using std::string;
using std::cout;
using std::endl;

struct ROUTING_TABLE_ENTRY {
    string destAddr;
    string intermediateAddr; // srcAddr = destAddr if neighbor
    int seqNum; // Destination SeqNum
    int cost; // HopCount to reach destination
    std::chrono::system_clock::time_point ttl; // Starting Timestamp at which this entry was created
    string tesla_hash;
    std::chrono::seconds tesla_disclosure_time;
    string hash; // Most recent authenticator hash
    std::queue<HERR> herr;

    ROUTING_TABLE_ENTRY(){
        this->destAddr = "ERR";
        this->intermediateAddr = "ERR";
        this->seqNum = -1;
        this->cost = -1;
        this->ttl = std::chrono::system_clock::now(); // Starting Timestamp at which this entry was created
        this->hash = "";
        this->tesla_hash = "ERR";
        this->tesla_disclosure_time = std::chrono::seconds(0);
    }

    ROUTING_TABLE_ENTRY(string destAddr, string intermediateAddr, int seqNum, int cost, std::chrono::system_clock::time_point ttl){
        this->destAddr = destAddr;
        this->intermediateAddr = intermediateAddr;
        this->seqNum = seqNum;
        this->cost = cost;
        this->ttl = ttl;
    }

    ROUTING_TABLE_ENTRY(string destAddr, string intermediateAddr, int seqNum, int cost, std::chrono::system_clock::time_point ttl, string hash){
        this->destAddr = destAddr;
        this->intermediateAddr = intermediateAddr;
        this->seqNum = seqNum;
        this->cost = cost;
        this->ttl = ttl;
        this->hash = hash;
    }

    ROUTING_TABLE_ENTRY(string destAddr, string intermediateAddr, int seqNum, int cost, std::chrono::system_clock::time_point ttl, string hash, HERR herr){
        this->destAddr = destAddr;
        this->intermediateAddr = intermediateAddr;
        this->seqNum = seqNum;
        this->cost = cost;
        this->ttl = ttl;
        this->hash = hash;
        this->insertHERR(herr);
    }

    void print() const {
        auto ttl_seconds = std::chrono::duration_cast<std::chrono::seconds>(ttl.time_since_epoch()).count();
        cout << "Routing entry: " << "destAddr: " << destAddr << ", intermediateAddr: " << intermediateAddr << ", seqNum: " << seqNum << ", cost: " << cost << ", ttl: " << ttl_seconds << " seconds, tesla_hash: " << tesla_hash << ", tesla_disclosure_time: " << tesla_disclosure_time.count() << " seconds, hash: " << hash << ", herr: ";
        
        std::queue<HERR> temp = herr;
        while (!temp.empty()) {
            cout << temp.front() << " ";
            temp.pop();
        }
        
        cout << endl;
    }

    std::tuple<string, std::chrono::seconds> getTeslaInfo() {
        if (tesla_hash.compare("ERR") == 0 || tesla_disclosure_time.count() == 0) {
            throw std::runtime_error("TESLA info not found");
        }
        return std::make_tuple(tesla_hash, tesla_disclosure_time);
    }

    void setTeslaInfo(string hash, std::chrono::seconds ttl) {
        this->tesla_hash = hash;
        this->tesla_disclosure_time = ttl;
    }

    friend std::ostream& operator<<(std::ostream& os, const ROUTING_TABLE_ENTRY& entry) {
        os << "{ destAddr: " << entry.destAddr << ", intermediateAddr: " << entry.intermediateAddr
           << ", seqNum: " << entry.seqNum << ", cost: " << entry.cost
           << ", ttl: " << std::chrono::duration_cast<std::chrono::seconds>(entry.ttl.time_since_epoch()).count() << " seconds, hash: " << entry.hash << " }";
        return os;
    }

    void insertHERR(const HERR& herr) {
        this->herr.push(herr);
        
        // If queue size exceeds 15, remove the oldest element
        while (this->herr.size() > 15) {
            this->herr.pop();
        }
    }

    HERR getMostRecentHERR() const { // TEMP: may replace queue with just singular herr
    if (herr.empty()) {
        throw std::runtime_error("Queue is empty");
    }
    return herr.back();
}
};
