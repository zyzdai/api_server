# encoding=utf-8
import argparse
import base64
import json
import os
import re
import ddddocr
import requests
from unrar import rarFile
from flask import Flask, request, jsonify, make_response, send_from_directory

parser = argparse.ArgumentParser(description="使用ddddocr搭建的最简api服务")
parser.add_argument("-p", "--port", type=int, default=9898)
parser.add_argument("--ocr", action="store_true", help="开启ocr识别")
parser.add_argument("--old", action="store_true", help="OCR是否启动旧模型")
parser.add_argument("--det", action="store_true", help="开启目标检测")

args = parser.parse_args()

app = Flask(__name__)

# ddddocr
class Server(object):
    def __init__(self, ocr=True, det=False, old=False):
        self.ocr_option = ocr
        self.det_option = det
        self.old_option = old
        self.ocr = None
        self.det = None
        if self.ocr_option:
            print("ocr模块开启")
            if self.old_option:
                print("使用OCR旧模型启动")
                self.ocr = ddddocr.DdddOcr(old=True)
            else:
                print("使用OCR新模型启动，如需要使用旧模型，请额外添加参数  --old开启")
                self.ocr = ddddocr.DdddOcr()
        else:
            print("ocr模块未开启，如需要使用，请使用参数  --ocr开启")
        if self.det_option:
            print("目标检测模块开启")
            self.det = ddddocr.DdddOcr(det=True)
        else:
            print("目标检测模块未开启，如需要使用，请使用参数  --det开启")

    def classification(self, img: bytes):
        if self.ocr_option:
            return self.ocr.classification(img)
        else:
            raise Exception("ocr模块未开启")

    def detection(self, img: bytes):
        if self.det_option:
            return self.det.detection(img)
        else:
            raise Exception("目标检测模块模块未开启")

    def slide(self, target_img: bytes, bg_img: bytes, algo_type: str):
        dddd = self.ocr or self.det or ddddocr.DdddOcr(ocr=False)
        if algo_type == 'match':
            return dddd.slide_match(target_img, bg_img)
        elif algo_type == 'compare':
            return dddd.slide_comparison(target_img, bg_img)
        else:
            raise Exception(f"不支持的滑块算法类型: {algo_type}")

server = Server(ocr=args.ocr, det=args.det, old=args.old)


def get_img(request, img_type='file', img_name='image'):
    if img_type == 'b64':
        img = base64.b64decode(request.get_data())
        try: # json str of multiple images
            dic = json.loads(img)
            img = base64.b64decode(dic.get(img_name).encode())
        except Exception as e: # just base64 of single image
            pass
    if img_type == 'file':
        img = request.files.get(img_name).read()
    return img

def getImgContent(method,url,headers,cookies,data='',allow_redirects=True):
    if method == 'GET':
        response = requests.get(url=url,headers=headers,cookies=cookies,allow_redirects=allow_redirects).content
    elif method == 'POST':
        response = requests.post(url=url,data=data,headers=headers,cookies=cookies,allow_redirects=allow_redirects).content
    return response
def set_ret(result, ret_type='text'):
    if ret_type == 'json':
        if isinstance(result, Exception):
            return json.dumps({"status": 200, "result": "", "msg": str(result)})
        else:
            return json.dumps({"status": 200, "result": result, "msg": ""})
        # return json.dumps({"succ": isinstance(result, str), "result": str(result)})
    else:
        if isinstance(result, Exception):
            return ''
        else:
            return str(result).strip()


@app.route('/<opt>/<img_type>', methods=['POST'])
@app.route('/<opt>/<img_type>/<ret_type>', methods=['POST'])
def ocr(opt, img_type='file', ret_type='text'):
    try:
        img = get_img(request, img_type)
        print(img)
        if opt == 'ocr':
            result = server.classification(img)
        elif opt == 'det':
            result = server.detection(img)
        else:
            raise f"<opt={opt}> is invalid"
        return set_ret(result, ret_type)
    except Exception as e:
        return set_ret(e, ret_type)

@app.route('/slide/<algo_type>/<img_type>', methods=['POST'])
@app.route('/slide/<algo_type>/<img_type>/<ret_type>', methods=['POST'])
def slide(algo_type='compare', img_type='file', ret_type='text'):
    try:
        target_img = get_img(request, img_type, 'target_img')
        bg_img = get_img(request, img_type, 'bg_img')
        result = server.slide(target_img, bg_img, algo_type)
        return set_ret(result, ret_type)
    except Exception as e:
        return set_ret(e, ret_type)

@app.route('/ping', methods=['GET'])
def ping():
    return "pong"

# tts
voiceMap = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
    "yunjian": "zh-CN-YunjianNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "yunxia": "zh-CN-YunxiaNeural",
    "yunyang": "zh-CN-YunyangNeural",
    "xiaobei": "zh-CN-liaoning-XiaobeiNeural",
    "xiaoni": "zh-CN-shaanxi-XiaoniNeural",
    "hiugaai": "zh-HK-HiuGaaiNeural",
    "hiumaan": "zh-HK-HiuMaanNeural",
    "wanlung": "zh-HK-WanLungNeural",
    "hsiaochen": "zh-TW-HsiaoChenNeural",
    "hsioayu": "zh-TW-HsiaoYuNeural",
    "yunjhe": "zh-TW-YunJheNeural",
}


def getVoiceById(voiceId):
    return voiceMap.get(voiceId)


# 删除html标签
def remove_html(string):
    regex = re.compile(r'<[^>]+>')
    return regex.sub('', string)


def createAudio(text, file_name, voiceId,rate):
    new_text = remove_html(text)
    print(f"Text without html tags: {new_text}")
    voice = getVoiceById(voiceId)
    rate = f"+{rate}%"
    if not voice:
        return "error params"

    pwdPath = os.getcwd()
    filePath = pwdPath + "/" + file_name
    dirPath = os.path.dirname(filePath)
    if not os.path.exists(dirPath):
        os.makedirs(dirPath)
    if not os.path.exists(filePath):
        # 用open创建文件 兼容mac
        open(filePath, 'a').close()

    script = 'edge-tts --rate='+rate+' --voice ' + voice + ' --text "' + new_text + '" --write-media ' + filePath
    os.system(script)
    # 上传到腾讯云COS云存储
    # uploadCos(filePath, file_name)
    return filePath


def getParameter(paramName):
    if request.args.__contains__(paramName):
        return request.args[paramName]
    return ""

@app.route('/dealAudio',methods=['POST','GET'])
def dealAudio():
    text = getParameter('text')
    file_name = getParameter('file_name')
    voice = getParameter('voice')
    rate = getParameter('rate')
    filePath = createAudio(text, file_name, voice,rate)
    r = os.path.split(filePath)
    print(r)
    try:
        response = make_response(
            send_from_directory(r[0], file_name, as_attachment=True))
        return response
    except Exception as e:
        return jsonify({"code": "异常", "message": "{}".format(e)})

def extract_rar(file_path, output_path):
    rar = rarFile(file_path)
    rar.extractall(output_path)
    rar.close()

@app.route('/rar')
def rar():
    pwdPath = os.getcwd()
    filePath = pwdPath + "/1.rar"
    dirPath = os.path.dirname(filePath)
    if not os.path.exists(dirPath):
        os.makedirs(dirPath)
    if not os.path.exists(filePath):
        # 用open创建文件 兼容mac
        open(filePath, 'a').close()
    url = 'https://beitai.cc/s/books/%E7%95%AA%E8%8C%84/%E9%9A%94%E8%83%B3%E5%91%9C%E5%91%9C/%E5%AD%A6%E5%A7%90%E5%88%AB%E6%80%95%EF%BC%8C%E6%88%91%E6%9D%A5%E4%BF%9D%E6%8A%A4%E4%BD%A0.rar'
    with open(filePath, 'wb') as f:
        f.write(requests.get(url).content)
        f.close()
    #extract_rar(filePath,pwdPath)
    print(os.listdir('/usr/bin'))
    print(os.listdir(dirPath))
    return f'welcome to my rar!'

@app.route('/tts')
def index():
    return 'welcome to my tts!'

if __name__ == '__main__':
    os.system('sudo apt-get install unrar')
    app.run(host="0.0.0.0", port=args.port)
