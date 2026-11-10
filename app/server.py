"""FaixaLab cloud entry point. Codespaces' private port supplies access control."""
import argparse
import os
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','7860')))
    args=parser.parse_args()
    from faixalab.remote_access import validate_server_settings
    validate_server_settings()
    if os.environ.get('CODESPACES')=='true':
        os.environ.setdefault('FAIXALAB_DATA_DIR','/workspaces/.faixalab-data')
    os.environ['PORT']=str(args.port)
    from faixalab.app import app
    if os.environ.get('FAIXALAB_QA')=='1':
        from fastapi.responses import HTMLResponse
        from starlette.routing import Route
        async def qa_mobile(request):
            return HTMLResponse('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#252a2e;display:grid;place-items:center;min-height:100vh"><iframe title="FaixaLab mobile 390" src="/" style="width:390px;height:844px;border:1px solid #46535c;border-radius:18px" allow="autoplay"></iframe></body></html>')
        app.router.routes.insert(0,Route('/__qa/mobile',qa_mobile))
    import uvicorn
    uvicorn.run(app,host=args.host,port=args.port,access_log=True,proxy_headers=True)


if __name__=='__main__':main()
