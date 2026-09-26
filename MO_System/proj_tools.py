from __future__ import annotations
import sys
from pathlib import Path

# Common tools for measurement projects
class ProjectTools:
    
    @staticmethod
    def inject_inst_libs(start_file: str | Path | None = None, libs_dir_name: str = "inst_libs"):
        """
        Find GUI root by walking upward, then inject <root>/<libs_dir_name> into sys.path.

        Returns:
            (root_dir, inst_lib_dir, injected)
        """
        
        base = Path(start_file or __file__).resolve().parent

        for folder in (base, *base.parents):
            inst_dir = folder / libs_dir_name
            if inst_dir.is_dir():
                inst_dir_str = str(inst_dir)
                if inst_dir_str not in sys.path:
                    sys.path.insert(0, inst_dir_str)
                    return folder, inst_dir, True
                return folder, inst_dir, False

        raise FileNotFoundError(f"Cannot find {libs_dir_name} from {base}")
        