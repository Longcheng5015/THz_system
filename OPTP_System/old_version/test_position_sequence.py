
import numpy as np


# def generate_position_sequence(iPos, step_array) -> list:
#     position_sequence = []
#     step_sequence = []
    
#     num_step_size = step_array.shape[1]
#     for step_idx in range(num_step_size):
#         step_size = step_array[0, step_idx]
#         step_NO = int(step_array[1, step_idx])  # 移动次数
        
#         # skip if step_NO is zero
#         if step_NO == 0 or step_size == 0:
#             continue
        
#         new_positions = iPos + (np.arange(step_NO)+1) * step_size  # 转换为mm
#         new_positions = np.round(new_positions, decimals=3)  # 保留3位小数
#         print(np.arange(step_NO)+1)
        
#         position_sequence.extend(new_positions.tolist())
#         # 注意：不要再加一次步长，直接用最后一个点
#         step_sequence.extend(([float(step_size)] * step_NO))
#         iPos = position_sequence[-1] #+ step_array[0, step_idx]  # 更新iPos为当前最后位置加上当前步长
        
#     if len(position_sequence) == 0:
#         position_sequence = [float(iPos)]
#         step_sequence = [0.0]
        
#     return position_sequence, step_sequence

def generate_position_sequence(iPos, step_array) -> list:
        position_sequence = []
        step_sequence = []
        stepNO_sequence = []
        num_step_size = step_array.shape[1]   # column number of the step array, number of step sizes
        
        for step_idx in range(num_step_size):
            step_size = step_array[0, step_idx]       # get step size, row 0
            step_NO   = int(step_array[1, step_idx])  # get step NO., row 1
            
            # Skip if step size or step NO is zero
            if step_size == 0 or step_NO == 0:
                continue
            
            if len(position_sequence) == 0:
                new_positions = iPos + np.arange(step_NO) * step_size  # for the first step size, start from iPos
            else: 
                new_positions = iPos + (np.arange(step_NO) + 1) * step_size  # for subsequent step sizes, start from last position + step_size

            new_positions = np.round(new_positions, 3)  # round to 3 decimal places to avoid floating point precision issues
            position_sequence.extend(new_positions.tolist())  # transform new_positions into list and append to overall position sequence
            step_sequence.extend(([float(step_size)] * step_NO))  # extend step size sequence in um
            stepNO_sequence.extend((list(range(1, step_NO + 1))))  # extend step NO. sequence
            iPos = position_sequence[-1]  # update iPos for next step_size
            
        if len(position_sequence) == 0:
            position_sequence = [iPos]  # if no steps defined, stay at initial position
            step_sequence = [0.0]       # step size is 0
            stepNO_sequence = [0]       # step NO. is 0

        return position_sequence, step_sequence, stepNO_sequence
    
# 示例
iPos = 10
step_array = np.array([[0.001, 0.003, 0.005],
                       [2, 2, 5]])
position_sequence = generate_position_sequence(iPos, step_array)
print(position_sequence)


# def add_sequence(start_T: float, step_T: float, NO_T: int) -> list:
#         """ Add temperature sequence from UI inputs."""
#         new_points = [start_T + i * step_T for i in range(NO_T)]
#         return new_points

# startT = 290.45
# stepT = 0.1
# NO_T = 10
# temp_sequence = add_sequence(startT, stepT, NO_T)
# for temp_idx, target_T in enumerate(temp_sequence):
#     target_T = np.round(target_T, 3)
#     print(f"Step {temp_idx}: Target Temperature = {target_T} K")
