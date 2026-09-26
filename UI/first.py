from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton,  QPlainTextEdit, QMessageBox

def handleCalc():        # signal slot function， 用来处理button按钮点击事件
    # 获取textEdit中的文本内容，并执行统计
    info= textEdit.toPlainText()   # 获取textEdit中对应的文本框内容, 返回纯文本
    
    # 统计过程
    # 薪资20000 以上 和 以下 的人员名单
    salary_above_20k = ''
    salary_below_20k = ''
    for line in info.splitlines():       # 把一个多行字符串按行拆分成列表
        if not line.strip():             # 去除一行开头和结尾的空白字符（空格、换行、制表符等）
            continue                     # 如果去除后为空字符串，说明这是一行空行 → 就跳过 (continue)，防止后面报错。
        parts = line.split(' ')          # 将每一行按空格拆成若干部分
        
        parts = [p for p in parts if p]  # 这是列表推导式，意思是：只保留不为空的项。组成一个新的列表，再赋值回 parts

        name,salary,age = parts          # 假设每行都有三部分数据（姓名、工资、年龄），然后将其分别赋值
        if int(salary) >= 20000:         # 将薪资字符串转换为整数进行比较
            salary_above_20k += name + '\n'
        else:
            salary_below_20k += name + '\n'

    QMessageBox.about(window,            # about() 显示“关于”消息框
                '统计结果',
                f'''薪资20000 以上的有：\n{salary_above_20k}
                \n薪资20000 以下的有：\n{salary_below_20k}'''
                )

# Create anApplication
app = QApplication()

window = QMainWindow()
window.resize(500, 400)
window.move(300, 310)
window.setWindowTitle('薪资统计')

textEdit = QPlainTextEdit(window)
textEdit.setPlaceholderText("请输入薪资表")
textEdit.move(10,25)
textEdit.resize(300,350)

button = QPushButton('统计', window)
button.move(380,80)
button.clicked.connect(handleCalc)   # 绑定按钮点击事件, 连接到signal slot--handleCalc函数

window.show()

app.exec() # PySide6 是 exec 而不是 exec_