#include <iostream>
#include <fstream>
#include <cstring>
#include <filesystem>
#define partSize 1000000 //1MB

int main(int argc, char *argv[]) {
	
    //std::string part;

    std::fstream file(argv[1], std::ios::in | std::ios::binary);

    // Check if the file is open
    if (!file) {
        std::cerr << "Error opening the file for Reading.";
        return 1;
    }    

    size_t strLength;
    file.read(reinterpret_cast<char*>(&strLength), sizeof(strLength));

    std::cout << strLength << std::endl;
    unsigned long parts = strLength/partSize;  


    
    std::string folder = "partions/";
    {
        std::string part = ".part";
        folder = folder + argv[1] + part;
    }

    
    char* buffer = new char[partSize+1];    
    for (unsigned long i=0; i<=parts;i++) {
        file.read(buffer, partSize);
        buffer[partSize] = '\0';
        std::string num = std::to_string(i);
        
        num= folder + num;
        
        
        std::cout << num << std::endl;
        
        std::ofstream filePart(num, std::ios::binary);
        size_t strLength2 = partSize+1; //+1 for the file ending
        filePart.write(reinterpret_cast<const char*>(&strLength2), sizeof(strLength2));     
        filePart.write(buffer, strLength2);
        filePart.close();

        file.seekg(partSize,std::ios_base::cur);
    }

    delete[] buffer;
    file.close();    

	return 0;
}