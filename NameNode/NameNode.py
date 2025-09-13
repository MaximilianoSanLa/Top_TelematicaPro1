# namenode_server.py
import math
import grpc
from concurrent import futures

import name_node_pb2 as pb
import name_node_pb2_grpc as pb_grpc

# ====== Configuración del DFS ======
BLOCK_SIZE = 64 * 1024 * 1024        # 64 MB                     # número de réplicas por bloque
DATANODES = [                        # DataNodes disponibles (host:port)
    "localhost:5002",
    "localhost:5003",
    "localhost:5004",
]
class NameNodeServicer(pb_grpc.NameNodeServicer):
    def PlanFileWrite(self, request:pb.PlanFileWriteRequest, context):
        file_name = request.file_name
        file_size = int(request.file_size)
        
        # Calcular número de bloques PRIMERO
        if file_size > 0:
            num_blocks = math.ceil(file_size / BLOCK_SIZE)#redondea hacia arriba
        else:
            num_blocks = 0 
        NumNodes=len(DATANODES)
        assignments=[]
        
        for i in range(num_blocks):
            assignments.append(pb.BlockAssignment(block_index=i, datanodes=[DATANODES[i%NumNodes]]))
            print(f"DEBUG: DATANODES = {DATANODES}")
        print(f"[PlanFileWrite] file={file_name} size={file_size} -> "
              f"block_size={BLOCK_SIZE} num_blocks={num_blocks}")
        
        # DEBUG: Imprimir el plan completo antes de enviarlo
        response = pb.PlanFileWriteResponse(block_size=BLOCK_SIZE, num_blocks=num_blocks, assignments=assignments)
        print("=== DEBUG PLAN ===")
        print(f"Response: {response}")
        for i, assignment in enumerate(assignments):
            print(f"Assignment {i}: block_index={assignment.block_index}, datanodes={list(assignment.datanodes)}")
        print("==================")
        
        return response
        
def serve(port: int = 50051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    pb_grpc.add_NameNodeServicer_to_server(NameNodeServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"NameNode gRPC escuchando en :{port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()



        

