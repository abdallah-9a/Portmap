import psutil

def get_listening_connections():
    connections_list = []
    
    for conn in psutil.net_connections(kind='inet'):
        
        if conn.status == 'LISTEN':
            
            port = conn.laddr.port
            pid = conn.pid
            process_name = "Unknown"
            
            if pid is not None:
                try:
                    process = psutil.Process(pid)
                    process_name = process.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                   pass
            
            connection_info = {
                "port": port,
                "pid": pid,
                "name": process_name
            }
            connections_list.append(connection_info)
            
    return connections_list
