"""Sistema de Recepção Nucleleste — roda na bandeja do Windows (perto do relógio), sem janela de console.

Dois modos:
  tray.pyw             ícone na bandeja (painel de controle). Se o servidor já roda como tarefa do Windows, só mostra o
                       ícone; se não, ele mesmo sobe o servidor dentro do processo.
  tray.pyw --servidor  só o servidor web (Waitress), sem janela nem ícone. É o que a tarefa "Sistema Nucleleste
                       (servidor)" executa no boot do Windows, antes de qualquer usuário entrar.
Usa apenas a API do Windows via ctypes, então funciona igual em Windows 10/11, 32 ou 64 bits.
"""
import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from ctypes import wintypes

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
MODO_SERVIDOR = '--servidor' in sys.argv
TAREFA = os.environ.get('NUCLELESTE_TAREFA', 'Sistema Nucleleste (servidor)')


# ---------------------------------------------------------------- pasta de dados e log (antes de importar o app)
def _pasta_dados():
    if os.environ.get('NUCLELESTE_DADOS'):
        return os.environ['NUCLELESTE_DADOS']
    marcador = os.path.join(QUI, 'local_dados.txt')  # gravado pelo instalador
    if os.path.exists(marcador):
        with open(marcador, encoding='utf-8-sig') as fh:
            p = fh.read().strip()
        if p:
            return p
    return os.path.join(QUI, 'dados')


DADOS = _pasta_dados()
os.environ['NUCLELESTE_DADOS'] = DADOS
os.makedirs(os.path.join(DADOS, 'logs'), exist_ok=True)
LOG = os.path.join(DADOS, 'logs', 'servidor.log' if MODO_SERVIDOR else 'nucleleste.log')
LOG_SERVIDOR = os.path.join(DADOS, 'logs', 'servidor.log')
try:
    if os.path.exists(LOG) and os.path.getsize(LOG) > 2_000_000:
        os.replace(LOG, LOG + '.1')
    _fh = open(LOG, 'a', buffering=1, encoding='utf-8', errors='replace')
    sys.stdout = sys.stderr = _fh
except OSError:
    pass


def log(*a):
    print(time.strftime('%d/%m/%Y %H:%M:%S'), *a, flush=True)


# ---------------------------------------------------------------- API do Windows
user32, shell32, kernel32 = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY, WM_CLOSE, WM_COMMAND, WM_NULL = 0x0002, 0x0010, 0x0111, 0x0000
WM_USER = 0x0400
WM_TRAY = WM_USER + 20
WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0203, 0x0205
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 0x10
NIIF_INFO = 1
MF_STRING, MF_GRAYED, MF_SEPARATOR, MF_POPUP = 0, 1, 0x800, 0x10
TPM_RIGHTBUTTON, TPM_BOTTOMALIGN, TPM_RETURNCMD = 2, 0x20, 0x100
MB_OK, MB_YESNO, MB_ICONINFORMATION, MB_ICONERROR, MB_ICONQUESTION, IDYES = 0, 4, 0x40, 0x10, 0x20, 6
CF_UNICODETEXT, GMEM_MOVEABLE = 13, 2
IMAGE_ICON, LR_LOADFROMFILE, SM_CXSMICON = 1, 0x10, 49


class GUID(ctypes.Structure):
    _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD), ('Data3', wintypes.WORD), ('Data4', ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('hWnd', wintypes.HWND), ('uID', wintypes.UINT), ('uFlags', wintypes.UINT),
                ('uCallbackMessage', wintypes.UINT), ('hIcon', wintypes.HICON), ('szTip', wintypes.WCHAR * 128),
                ('dwState', wintypes.DWORD), ('dwStateMask', wintypes.DWORD), ('szInfo', wintypes.WCHAR * 256),
                ('uVersion', wintypes.UINT), ('szInfoTitle', wintypes.WCHAR * 64), ('dwInfoFlags', wintypes.DWORD),
                ('guidItem', GUID), ('hBalloonIcon', wintypes.HICON)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', wintypes.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HINSTANCE), ('hIcon', wintypes.HICON), ('hCursor', wintypes.HANDLE),
                ('hbrBackground', wintypes.HBRUSH), ('lpszMenuName', wintypes.LPCWSTR), ('lpszClassName', wintypes.LPCWSTR)]


def _assinaturas():
    P, V = ctypes.c_void_p, ctypes.c_void_p
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]; user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]; user32.DispatchMessageW.restype = LRESULT
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, V]
    user32.TrackPopupMenu.restype = wintypes.UINT
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.SetMenuDefaultItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]; user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]; user32.SetClipboardData.restype = wintypes.HANDLE
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]; kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]; kernel32.GlobalLock.restype = P
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.CreateMutexW.argtypes = [P, wintypes.BOOL, wintypes.LPCWSTR]; kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]; kernel32.GetModuleHandleW.restype = wintypes.HMODULE


_assinaturas()


def aviso(texto, titulo='Sistema Nucleleste', icone=MB_ICONINFORMATION):
    return user32.MessageBoxW(None, texto, titulo, MB_OK | icone)


def abrir(caminho_ou_url):
    try:
        shell32.ShellExecuteW(None, 'open', caminho_ou_url, None, None, 1)
    except Exception:
        log('falha ao abrir', caminho_ou_url, traceback.format_exc())


def copiar(texto):
    """Copia texto para a área de transferência."""
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        dados = (texto + '\0').encode('utf-16-le')
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dados))
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, dados, len(dados))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)
        return True
    finally:
        user32.CloseClipboard()


def enderecos_rede():
    """IPs IPv4 desta máquina visíveis na rede local (sem loopback/APIPA)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))  # não envia nada; só descobre a interface de saída
        ips.append(s.getsockname()[0]); s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except OSError:
        pass
    vistos, saida = set(), []
    for ip in ips:
        if ip.startswith(('127.', '169.254.', '0.')) or ip in vistos:
            continue
        vistos.add(ip); saida.append(ip)
    return saida


def porta_aberta(porta, tempo=1.0):
    try:
        with socket.create_connection(('127.0.0.1', porta), timeout=tempo):
            return True
    except OSError:
        return False


def tarefa_existe():
    """True se o servidor é gerenciado pela tarefa do Windows (inicia no boot)."""
    if os.environ.get('NUCLELESTE_MODO_EXTERNO') == '1':  # usado nos testes
        return True
    try:
        r = subprocess.run(['schtasks', '/Query', '/TN', TAREFA], capture_output=True, creationflags=0x08000000, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def rodar_servidor():
    """Modo --servidor: sobe só o servidor web e fica nele (sem janela). Reiniciado pela tarefa se cair."""
    mutex = kernel32.CreateMutexW(None, False, 'Global\\NucleleshteServidorUnico')
    if kernel32.GetLastError() == 183:
        log('já existe um servidor em execução; saindo')
        return 0
    from app import create_app, versao
    from waitress.server import create_server
    app = create_app(avisos_automaticos=True)
    porta = int(app.config['PORTA'])
    try:
        # 48 threads: até 24 consultas do chat ficam "seguradas" esperando mensagens (tempo real) e as demais telas continuam livres
        srv = create_server(app, host='0.0.0.0', port=porta, threads=48, ident='Nucleleste')
    except OSError as e:
        log('porta', porta, 'indisponível:', e)
        return 1  # código de erro: a tarefa tenta de novo em 1 minuto
    log('servidor (modo serviço) no ar na porta', porta, '| dados:', DADOS, '| versão', versao())
    srv.run()
    return 0


# ---------------------------------------------------------------- aplicativo
ID_ABRIR, ID_LOCAL, ID_PROG, ID_DADOS, ID_BKPDIR, ID_LOG, ID_BACKUP, ID_SOBRE, ID_SAIR = 1001, 1002, 1010, 1011, 1012, 1013, 1020, 1090, 1099
ID_REDE0 = 1200


class Bandeja:
    def __init__(self):
        from app import create_app, versao  # importa só depois de definir NUCLELESTE_DADOS
        self.versao = versao()
        self.app = create_app(avisos_automaticos=True)
        self.porta = int(self.app.config['PORTA'])
        self.servidor = None
        self.externo = False  # True: servidor gerenciado pela tarefa do Windows
        self.erro_servidor = None
        self.urls_rede = []
        self.hwnd = None
        self.hicon = None
        self.msg_taskbar = user32.RegisterWindowMessageW('TaskbarCreated')
        self._wndproc = WNDPROC(self._proc)  # mantém referência viva

    # --- servidor
    def iniciar_servidor(self):
        from waitress.server import create_server
        try:
            self.servidor = create_server(self.app, host='0.0.0.0', port=self.porta, threads=48, ident='Nucleleste')
        except OSError as e:
            if porta_aberta(self.porta):
                # já há um servidor do sistema respondendo nesta porta (outra cópia/tarefa): só mostra o ícone
                log('porta', self.porta, 'já atendida por outro servidor; a bandeja será apenas o painel')
                self.externo = True
                return True
            self.erro_servidor = str(e)
            log('não foi possível abrir a porta', self.porta, e)
            return False
        threading.Thread(target=self.servidor.run, daemon=True, name='waitress').start()
        log('servidor no ar na porta', self.porta, '| dados:', DADOS, '| versão', self.versao)
        return True

    @property
    def url_local(self):
        return 'http://localhost:%d' % self.porta

    def atualizar_urls(self):
        self.urls_rede = ['http://%s:%d' % (ip, self.porta) for ip in enderecos_rede()]
        nome = socket.gethostname()
        if nome:
            self.urls_rede.append('http://%s:%d' % (nome, self.porta))

    # --- ícone
    def _nid(self, flags):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd, nid.uID, nid.uFlags, nid.uCallbackMessage, nid.hIcon = self.hwnd, 1, flags, WM_TRAY, self.hicon
        no_ar = self.servidor or (self.externo and porta_aberta(self.porta, .3))
        nid.szTip = ('Sistema Nucleleste — %s' % ('no ar (porta %d)' % self.porta if no_ar else
                                                  'iniciando...' if self.externo else 'ERRO: porta em uso'))[:127]
        return nid

    def adicionar_icone(self):
        return bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid(NIF_MESSAGE | NIF_ICON | NIF_TIP))))

    def balao(self, titulo, texto):
        nid = self._nid(NIF_INFO)
        nid.szInfoTitle, nid.szInfo, nid.dwInfoFlags = titulo[:63], texto[:255], NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def remover_icone(self):
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid(0)))

    # --- menu
    def montar_menu(self):
        self.atualizar_urls()
        m = user32.CreatePopupMenu()
        ap = lambda flags, ident, texto: user32.AppendMenuW(m, flags, ident, texto)
        if self.externo:
            no_ar = porta_aberta(self.porta, .5)
            ap(MF_STRING | MF_GRAYED, 0, 'Sistema Nucleleste v%s — %s (porta %d)' % (
                self.versao, 'no ar, inicia com o Windows' if no_ar else 'INICIANDO... aguarde', self.porta))
        elif self.servidor:
            ap(MF_STRING | MF_GRAYED, 0, 'Sistema Nucleleste v%s — no ar (porta %d)' % (self.versao, self.porta))
        else:
            ap(MF_STRING | MF_GRAYED, 0, 'ERRO: a porta %d já está em uso' % self.porta)
        ap(MF_SEPARATOR, 0, None)
        ap(MF_STRING, ID_ABRIR, 'Abrir o sistema no navegador')
        ap(MF_SEPARATOR, 0, None)
        ap(MF_STRING | MF_GRAYED, 0, 'Endereços (clique para copiar):')
        ap(MF_STRING, ID_LOCAL, 'Neste computador:  %s' % self.url_local)
        for i, u in enumerate(self.urls_rede):
            rotulo = 'Na rede (outros PCs):  ' if i < len(self.urls_rede) - 1 else 'Na rede, pelo nome:  '
            ap(MF_STRING, ID_REDE0 + i, rotulo + u)
        ap(MF_SEPARATOR, 0, None)
        ap(MF_STRING, ID_PROG, 'Ver o local do programa')
        ap(MF_STRING, ID_DADOS, 'Ver a pasta dos dados (banco de dados)')
        ap(MF_STRING, ID_BKPDIR, 'Ver a pasta dos backups')
        ap(MF_STRING, ID_LOG, 'Ver o registro de funcionamento (log)')
        ap(MF_SEPARATOR, 0, None)
        ap(MF_STRING, ID_BACKUP, 'Fazer backup agora')
        ap(MF_STRING, ID_SOBRE, 'Sobre / informações')
        ap(MF_SEPARATOR, 0, None)
        ap(MF_STRING, ID_SAIR, 'Fechar este ícone (o sistema continua no ar)' if self.externo else 'Sair (encerra o sistema para todos)')
        user32.SetMenuDefaultItem(m, ID_ABRIR, 0)
        return m

    def mostrar_menu(self):
        m = self.montar_menu()
        pt = wintypes.POINT(); user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)  # necessário para o menu fechar ao clicar fora
        cmd = user32.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN | TPM_RETURNCMD, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(m)
        if cmd:
            self.comando(cmd)

    # --- ações
    def comando(self, cmd):
        try:
            if cmd == ID_ABRIR:
                abrir(self.url_local)
            elif cmd == ID_LOCAL:
                copiar(self.url_local); self.balao('Endereço copiado', self.url_local)
            elif ID_REDE0 <= cmd < ID_REDE0 + 50:
                self.atualizar_urls()
                u = self.urls_rede[cmd - ID_REDE0]
                copiar(u); self.balao('Endereço copiado', u + '\nCole no navegador de outro computador da rede.')
            elif cmd == ID_PROG:
                abrir(QUI)
            elif cmd == ID_DADOS:
                abrir(DADOS)
            elif cmd == ID_BKPDIR:
                p = os.path.join(DADOS, 'backups'); os.makedirs(p, exist_ok=True); abrir(p)
            elif cmd == ID_LOG:
                abrir(LOG_SERVIDOR if self.externo and os.path.exists(LOG_SERVIDOR) else LOG)
            elif cmd == ID_BACKUP:
                threading.Thread(target=self.fazer_backup, daemon=True).start()
            elif cmd == ID_SOBRE:
                self.atualizar_urls()
                aviso('Sistema de Recepção Nucleleste\nVersão %s\n\nNeste computador: %s\n%s\n\nPrograma: %s\nDados: %s\n\n%s\n'
                      'Dica: dê um clique duplo no ícone para abrir o sistema.'
                      % (self.versao, self.url_local, '\n'.join('Na rede: ' + u for u in self.urls_rede), QUI, DADOS,
                         'O sistema roda como tarefa do Windows: liga junto com o computador, mesmo sem ninguém logado.'
                         if self.externo else 'Modo bandeja: o sistema roda enquanto este ícone estiver aberto.'))
            elif cmd == ID_SAIR:
                if self.externo:
                    self.encerrar()  # só o ícone; o servidor segue como tarefa do Windows
                elif user32.MessageBoxW(None, 'Encerrar o Sistema Nucleleste?\n\nOs outros computadores da rede ficarão sem acesso '
                                        'até ele ser aberto de novo.', 'Sair', MB_YESNO | MB_ICONQUESTION) == IDYES:
                    self.encerrar()
        except Exception:
            log('erro no comando', cmd, traceback.format_exc())

    def fazer_backup(self):
        try:
            from app import cli
            destino = cli.backup()
            self.balao('Backup concluído', os.path.basename(destino) if destino else 'Sem banco para copiar.')
        except Exception:
            log('falha no backup', traceback.format_exc())
            self.balao('Falha no backup', 'Veja o registro de funcionamento (log).')

    def encerrar(self):
        log('encerrando')
        self.remover_icone()
        try:
            if self.servidor:
                self.servidor.close()
        except Exception:
            pass
        user32.PostQuitMessage(0)
        os._exit(0)

    # --- janela oculta que recebe as mensagens do ícone
    def _proc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_TRAY:
                if lp == WM_LBUTTONDBLCLK:
                    self.comando(ID_ABRIR)
                elif lp == WM_RBUTTONUP:
                    self.mostrar_menu()
                return 0
            if msg == WM_COMMAND:
                self.comando(wp & 0xFFFF)
                return 0
            if msg == self.msg_taskbar:  # o Explorer reiniciou: recria o ícone
                self.adicionar_icone()
                return 0
            if msg == WM_CLOSE:
                self.encerrar()
                return 0
        except Exception:
            log('erro na janela', traceback.format_exc())
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def executar(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = self._wndproc, hinst, 'NucleleshteBandeja'
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(0, 'NucleleshteBandeja', 'Nucleleste', 0, 0, 0, 0, 0, None, None, hinst, None)
        tam = user32.GetSystemMetrics(SM_CXSMICON) or 16
        ico = os.path.join(QUI, 'nucleleste.ico')
        self.hicon = user32.LoadImageW(None, ico, IMAGE_ICON, tam, tam, LR_LOADFROMFILE)
        self.externo = tarefa_existe()
        if self.externo:
            log('servidor gerenciado pela tarefa do Windows; aguardando a porta', self.porta)
            for _ in range(60):
                if porta_aberta(self.porta):
                    break
                time.sleep(1)
            self.servidor = None
        elif not self.iniciar_servidor():
            self.adicionar_icone()
            aviso('Não foi possível iniciar o sistema: a porta %d já está em uso por outro programa.\n\n'
                  'Feche o outro programa ou altere a porta (arquivo config.json na pasta dos dados).\n\nDetalhe: %s'
                  % (self.porta, self.erro_servidor), icone=MB_ICONERROR)
            self.remover_icone()
            return 1
        ok = False
        for _ in range(30):  # a bandeja pode ainda não existir logo após o logon
            if self.adicionar_icone():
                ok = True; break
            time.sleep(2)
        log('ícone da bandeja:', 'ok' if ok else 'FALHOU')
        self.atualizar_urls()
        self.balao('Sistema Nucleleste em execução' if not self.externo else 'Sistema Nucleleste no ar',
                   'Neste PC: %s\nNa rede: %s\nClique duplo no ícone para abrir.' % (self.url_local, self.urls_rede[0] if self.urls_rede else '-'))
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        return 0


def main():
    if MODO_SERVIDOR:
        try:
            return rodar_servidor()
        except Exception:
            log('erro fatal no servidor', traceback.format_exc())
            return 1
    # só uma cópia por vez; abrir de novo apenas abre o navegador
    mutex = kernel32.CreateMutexW(None, False, 'Global\\NucleleshteBandejaUnica')
    if ctypes.get_last_error() == 183 or kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        try:
            porta = int(os.environ.get('NUCLELESTE_PORTA') or 0)
            if not porta:
                from app import carregar_config
                porta = int(carregar_config()['porta'])
        except Exception:
            porta = 8080
        abrir('http://localhost:%d' % porta)
        return 0
    try:
        return Bandeja().executar()
    except Exception:
        log('erro fatal', traceback.format_exc())
        aviso('O Sistema Nucleleste não conseguiu iniciar.\n\nDetalhes no arquivo:\n%s' % LOG, icone=MB_ICONERROR)
        return 1


if __name__ == '__main__':
    sys.exit(main())
