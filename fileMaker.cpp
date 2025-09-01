#include <iostream>
#include <fstream>
#include <cstring>
#include <algorithm>
#define fileSize 5000000

int main(int argc, char *argv[]) {
    std::string message = "d";

    //std::cout << "Creating message";
    {   //Para no gastar 10MB de ram
        char A [fileSize] = {0};
        std::fill_n(A, (fileSize - 1), 'A');
        message = A;
    }

    //std::cout << message;

    // Open a binary file for writing
    std::ofstream file(argv[1], std::ios::binary);

    // Check if the file is open
    if (!file) {
        std::cerr << "Error opening the file for writing.";
        return 1;
    }

    size_t strLength = message.length();
    file.write(reinterpret_cast<const char*>(&strLength),
        sizeof(strLength));    

    // Write the string to the binary file
    file.write(message.c_str(), strLength);

    // Close the file
    file.close();        

	return 0;
}
