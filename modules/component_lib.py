# This is to set the path for the module to be imported correctly when running the script directly
if __name__ == "__main__":
    import sys
    # open config file to get the project path
    with open("../configs/proj_folder_path.txt", "r") as f:
        lines = f.readlines()
        project_path = lines[0].strip()
        sys.path.append(project_path)



class ComponentLib:
    """
    ComponentLib is a class that stores the information of a component library.
    It returns related information of the library based on the input query, such as the name, path, and symbols.
    """
    def __init__(self, lib_name: str, lib_path: str):
        self.lib_name = lib_name
        self.lib_path = lib_path
        self.symbols = []  # List of symbols in the library

    def add_symbol(self, symbol_name: str):
        """
        Add a symbol to the library.
        """
        self.symbols.append(symbol_name)