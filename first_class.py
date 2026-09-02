from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton,  QPlainTextEdit,QMessageBox

class Stats:
    def __init__(self):
        self.window = QMainWindow()
        self.window.resize(500, 400)
        self.window.move(300, 300)
        self.window.setWindowTitle('薪资统计')

        self.textEdit = QPlainTextEdit(self.window)
        self.textEdit.setPlaceholderText("请输入薪资表")
        self.textEdit.move(10, 25)
        self.textEdit.resize(300, 350)

        self.button = QPushButton('统计', self.window)
        self.button.move(380, 80)

        self.button.clicked.connect(self.handleCalc)


    def handleCalc(self):
        info = self.textEdit.toPlainText()   # 获取textEdit中对应的文本框内容, 返回纯文本
    
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

        QMessageBox.about(self.window,            # about() 显示“关于”消息框
                    '统计结果',
                    f'''薪资20000 以上的有：\n{salary_above_20k}
                    \n薪资20000 以下的有：\n{salary_below_20k}'''
                    )
    

app = QApplication()
stats = Stats()
stats.window.show()
app.exec()