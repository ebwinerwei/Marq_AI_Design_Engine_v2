"""Optional approved commercial API connection; no platform-wide configuration."""
import base64,json,secrets,urllib.request
def commercial(cfg,kind,body):
    key=cfg['token'];model=cfg[kind+'Model']
    if kind=='text':
        url='https://api.openai.com/v1/responses'
        schema={'type':'object','properties':{'narrative':{'type':'string'},'mode':{'type':'string','enum':['H','V','wave']},'wave':{'type':'string','enum':['234565432','234323432','654323456','234555432','234567']}},'required':['narrative','mode','wave'],'additionalProperties':False}
        data=json.dumps({'model':model,'store':False,'instructions':'建築設計の日本語説明を提案する。確定済みの数量や所在地の法令適合を推測しない。','input':json.dumps(body,ensure_ascii=False),'text':{'format':{'type':'json_schema','name':'marq_design','strict':True,'schema':schema}}}).encode()
        content='application/json'
    else:
        url='https://api.openai.com/v1/images/edits'
        from .image_edit import edit_request
        data,content=edit_request(model,body)
    req=urllib.request.Request(url,data=data,headers={'Content-Type':content,'Authorization':'Bearer '+key})
    class Direct(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a):return None
    try:
        with urllib.request.build_opener(Direct()).open(req,timeout=150) as resp:
            result=json.loads(resp.read(40*1024*1024))
    except urllib.error.HTTPError as exc:
        detail={400:'モデルの画像編集・マスク・指定寸法への対応を確認してください',
                401:'APIキーを確認してください',403:'モデルの利用権限を確認してください',
                429:'利用枠または混雑状況を確認してください'}.get(exc.code,'提供元の状態をご確認ください')
        raise ValueError(f'AIサービス HTTP {exc.code} · {detail}') from exc
    except (urllib.error.URLError,TimeoutError) as exc:
        raise ValueError('AIサービスに接続できません。通信状態を確認して再実行してください') from exc
    if kind=='image':return {'image':'data:image/png;base64,'+result['data'][0]['b64_json']}
    return json.loads(''.join(v['text'] for msg in result['output'] for v in msg.get('content',[]) if v.get('type')=='output_text'))
