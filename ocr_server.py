# encoding=utf-8
import argparse
import base64
import json
import os
import re
import time
import zipfile
import ddddocr
import requests
import rarfile
import uuid
from flask import Flask, request, jsonify, make_response, send_from_directory
import execjs

rarfile.UNRAR_TOOL = "./unrar"
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
        try:  # json str of multiple images
            dic = json.loads(img)
            img = base64.b64decode(dic.get(img_name).encode())
        except Exception as e:  # just base64 of single image
            pass
    if img_type == 'file':
        img = request.files.get(img_name).read()
    return img


def getImgContent(method, url, headers, cookies, data='', allow_redirects=True):
    if method == 'GET':
        response = requests.get(url=url, headers=headers, cookies=cookies, allow_redirects=allow_redirects).content
    elif method == 'POST':
        response = requests.post(url=url, data=data, headers=headers, cookies=cookies,
                                 allow_redirects=allow_redirects).content
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


def createAudio(text, file_name, voiceId, rate):
    file_name = f'{uuid.uuid4()}.mp3'
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

    script = 'edge-tts --rate=' + rate + ' --voice ' + voice + ' --text "' + new_text + '" --write-media ' + filePath
    os.system(script)
    # 上传到腾讯云COS云存储
    # uploadCos(filePath, file_name)
    return filePath


def getParameter(paramName):
    if request.args.__contains__(paramName):
        return request.args[paramName]
    return ""


@app.route('/dealAudio', methods=['POST', 'GET'])
def dealAudio():
    clear_zip_file()
    text = getParameter('text')
    if len(text)<=0:
        return jsonify({"code": "异常", "message": "text参数不能为空"})
    file_name = getParameter('file_name')
    if len(file_name)<=0:
        return jsonify({"code": "异常", "message": "filename参数不能为空"})
    voice = getParameter('voice')
    rate = getParameter('rate')
    filePath = createAudio(text, file_name, voice, rate)
    r = os.path.split(filePath)
    print(r)
    try:
        response = make_response(
            send_from_directory(r[0], r[1], as_attachment=True))
        return response
    except Exception as e:
        return jsonify({"code": "异常", "message": "{}".format(e)})


def rar2zip(rar_file,filename):
    rar = rarfile.RarFile(rar_file)
    rar.extractall(os.getcwd() + '/')
    rar.close()
    namelist = rar.namelist()
    print(namelist)
    zip_file = f'{uuid.uuid4()}.zip'
    compress_files_to_zip(namelist, zip_file)
    for file in namelist:
        os.remove(file)
    os.remove(rar_file)
    # 清除超过1天的zip文件
    clear_zip_file()
    return zip_file


def clear_zip_file(sec=120):
    zip_file_list = os.listdir(os.getcwd())
    for file in zip_file_list:
        if file.endswith('.zip') or file.endswith('mp3'):
            zip_file_time = os.path.getmtime(file)
            if (time.time() - zip_file_time) > sec:
                os.remove(file)

def compress_files_to_zip(file_paths, zip_file_path):
    with zipfile.ZipFile(zip_file_path, 'w') as zipf:
        for file_path in file_paths:
            zipf.write(file_path)


@app.route('/rar2zip')
def r2z():
    clear_zip_file()
    rarurl = getParameter('rarurl')
    if len(rarurl)<=0 or rarurl.find('http')==-1:
        return jsonify({"code": "异常", "message": "rarurl参数异常"})
    filename = getParameter('filename')
    if len(filename)<=0:
        return jsonify({"code": "异常", "message": "filename参数不能为空"})
    pwdPath = os.getcwd()
    filePath = pwdPath + f"/{filename}.rar"
    dirPath = os.path.dirname(filePath)
    if not os.path.exists(dirPath):
        os.makedirs(dirPath)
    if not os.path.exists(filePath):
        # 用open创建文件 兼容mac
        open(filePath, 'a').close()
    print(rarurl)
    with open(filePath, 'wb') as f:
        f.write(requests.get(rarurl).content)
        f.close()
    zipName = rar2zip(filePath,filename)
    r = os.path.split(filePath)
    try:
        response = make_response(
            send_from_directory(r[0], zipName, as_attachment=True))
        return response
    except Exception as e:
        return jsonify({"code": "异常", "message": "{}".format(e)})

@app.route('/clearzip')
def clearzip():
    sec = getParameter('sec')
    clear_zip_file(float(sec))
    return f'清除超过{sec}秒的zip文件!'

@app.route('/tts')
def index():
    return 'welcome to my tts!'


def getXBogus(ms, data):
    node = execjs.get()
    with open('xb.js', encoding='utf-8') as f:
        js_code = f.read()
    ctx = node.compile(js_code)
    xb = ctx.call('getXBogus', ms, data)
    return xb
    
def getMsToken():
    node = execjs.get()
    with open('xb.js', encoding='utf-8') as f:
        js_code = f.read()
    ctx = node.compile(js_code)
    ms = ctx.call('getMsToken')
    return ms
    
@app.route('/getXBogus')
def xb():
    msToken = getParameter('msToken')
    data = getParameter('data')
    xb = getXBogus(msToken,data)
    return jsonify({"ms": "{}".format(xb)})

@app.route('/getMsToken')
def ms():
    ms = getMsToken()
    return jsonify({"ms": "{}".format(ms)})

def genshinvoice(Text,Speaker,SDP=0.5,Noise=0.6,Noise_W=0.9,Length=1,Language="auto",Weight=0.7,Yuyi=''):
    headers = {
        "content-type": "application/json",
        "referer": "https://v2.genshinvoice.top/?",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = "https://v2.genshinvoice.top/run/predict"
    data = {
        "data": [
            Text,
            Speaker,
            float(SDP),
            float(Noise),
            float(Noise_W),
            float(Length),
            Language,
            None,
            Yuyi,
            "Text prompt",
            "",
            float(Weight)
        ],
        "event_data": None,
        "fn_index": 0,
        "session_hash": "2a8v7iq0o0o"
    }
    print(data)
    data = json.dumps(data, separators=(',', ':'))
    response = requests.post(url, headers=headers, data=data)
    result = response.json()
    print(result)
    name = result['data'][1]['name']
    url = 'https://v2.genshinvoice.top/file=' + name
    return url


@app.route('/genshininvoice', methods=['GET', 'POST'])
def genshininvoice_api():
    clear_zip_file()
    # GET
    if request.method == 'GET':
        text = request.args.get('text')
        speaker = request.args.get('speaker')
        sdp = request.args.get('sdp')
        noise = request.args.get('noise')
        noise_w = request.args.get('noise_w')
        length = request.args.get('length')
        language = request.args.get('language')
        weight = request.args.get('weight')
        yuyi = request.args.get('yuyi')
        url = genshinvoice(text, speaker, sdp, noise, noise_w, length, language, weight, yuyi)
        res = requests.get(url)
        file_name = f'{uuid.uuid4()}.wav'
        pwdPath = os.getcwd()
        filePath = pwdPath + "/" + file_name
        with open(filePath, 'wb') as f:
            f.write(res.content)
        r = os.path.split(filePath)
        try:
            response = make_response(
                send_from_directory(r[0], r[1], as_attachment=True))
            return response
        except Exception as e:
            return jsonify({"code": "异常", "message": "{}".format(e)})

def AIAudio(Text, Speaker, SDP=0.5, Noise=0.6, Noise_W=0.8, Length=1):
    headers = {
        "content-type": "application/json",
        "referer": "https://v2.genshinvoice.top/?",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    Speakers = {"taffy": "Taffy-Bert-VITS2", "TF": "LittleTaffy-Bert-VITS2", "Azuma": "Azuma-Bert-VITS2",
                "LAPLACE": "LAPLACE-Bert-VITS2", "nine": "nine1-Bert-VITS2",
                "Carol": "Carol-Bert-VITS2",
                "otto": "otto-Bert-VITS2",
                "Nana7mi": "Nana7mi-Bert-VITS2",
                "XingTong": "XingTong-Bert-VITS2",
                "Ava": "Ava-Bert-VITS2",
                "Aatrox": "Aatrox-Bert-VITS2",
                "Eileen": "Eileen-Bert-VITS2",
                "Bella": "Bella-Bert-VITS2",
                "ShanBao": "ShanBao-Bert-VITS2",
                "Bekki": "Bekki-Bert-VITS2",
                "Echo": "Echo-Bert-VITS2",
                "WaiMai": "maimai-Bert-VITS2",
                "Lumi": "Lumi-Bert-VITS2",
                "Wenjing": "Wenjing-Bert-VITS2","Diana": "Diana-Bert-VITS2"}
    url = f"https://www.modelscope.cn/api/v1/studio/xzjosh/{Speakers[Speaker]}/gradio/run/predict"
    data = {
        "data": [
            Text,
            Speaker,
            float(SDP),
            float(Noise),
            float(Noise_W),
            float(Length)
        ],
        "event_data": None,
        "fn_index": 0,
        "dataType": [
            "textbox",
            "dropdown",
            "slider",
            "slider",
            "slider",
            "slider"
        ],
        "session_hash": "dltfoxag7rb"
    }
    data = json.dumps(data, separators=(',', ':'))
    response = requests.post(url, headers=headers, data=data)
    result = response.json()
    name = result['data'][1]['name']
    audio = f'https://www.modelscope.cn/api/v1/studio/xzjosh/{Speakers[Speaker]}/gradio/file=' + name
    return audio
@app.route('/AIAudio', methods=['GET', 'POST'])
def aiaudio_api():
    clear_zip_file()
    # GET
    if request.method == 'GET':
        text = request.args.get('text')
        speaker = request.args.get('speaker')
        sdp = request.args.get('sdp')
        noise = request.args.get('noise')
        noise_w = request.args.get('noise_w')
        length = request.args.get('length')
        url = AIAudio(text, speaker, sdp, noise, noise_w, lengt)
        res = requests.get(url)
        file_name = f'{uuid.uuid4()}.wav'
        pwdPath = os.getcwd()
        filePath = pwdPath + "/" + file_name
        with open(filePath, 'wb') as f:
            f.write(res.content)
        r = os.path.split(filePath)
        try:
            response = make_response(
                send_from_directory(r[0], r[1], as_attachment=True))
            return response
        except Exception as e:
            return jsonify({"code": "异常", "message": "{}".format(e)})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=args.port)
