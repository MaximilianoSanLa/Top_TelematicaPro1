#include <iostream>
#include <fstream>
#include <cstring>
#include <filesystem>
#ifdef _WIN32
#include <string>
#endif
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

    { //Error case 2
    file.seekg (0, file.end);
    size_t length = file.tellg();
    file.seekg (0, file.beg);    
    std::cout << "Tamaño del archivo (en bytes): " <<length << std::endl;

    if (length < partSize) {
        std::cout << "El archivo ya es más pequeño que el tamaño de las partes";
        return 2;
    }

    std::cout << "Tamaño del mensaje de los datos dentro del arhivo: " << strLength << std::endl;
    //test?
        strLength = length;
    //test end
    }
    unsigned long parts = strLength/partSize;  


#ifdef _linux_
    std::string folder = "partions/";
    {
        std::string part = ".part";
        folder = folder + argv[1] + part;
    }


#else
    std::string folder = argv[1];
    {
        std::string part = ".part";
        folder = folder + part;
    }
#endif // 



    
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

        //file.seekg(partSize, file.cur);
        file.seekg(partSize*(i+1));
    }

    delete[] buffer;
    file.close();    

	return 0;
}