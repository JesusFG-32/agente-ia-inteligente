"""
adaptadores/sistema.py
======================
Adaptador para monitorear recursos generales del sistema (CPU, RAM, Disco).
Soporta monitoreo local usando `psutil` o monitoreo remoto via SSH (Paramiko).
"""

import logging
import re
from typing import Optional, Any
import psutil
import paramiko

logger = logging.getLogger("agente-ia.sistema")


class AdaptadorSistema:
    """
    Monitorea recursos generales (CPU, RAM, Disco).

    Uso:
        sys = AdaptadorSistema(ssh_client=nginx_client) # o pasar credenciales
        metricas = sys.obtener_metricas()
    """

    def __init__(
        self,
        host: str = "",
        user: str = "",
        key_path: str = "",
        password: str = "",
        auth_method: str = "key",
        port: int = 22,
        ssh_client: Optional[paramiko.SSHClient] = None,
    ) -> None:
        self.host = host
        self.user = user
        self.key_path = key_path
        self.password = password
        self.auth_method = auth_method.lower() if auth_method else "key"
        self.port = port
        self._cliente_ssh = ssh_client
        self._externo = ssh_client is not None or bool(host)
        self._auto_conectado = False

    def _conectar_ssh(self) -> None:
        """Establece la conexión SSH si se configuraron credenciales y no hay cliente provisto o está inactivo."""
        if self._cliente_ssh is not None:
            transport = self._cliente_ssh.get_transport()
            if transport is not None and transport.is_active():
                return
            logger.warning("Conexión SSH para sistema inactiva o cerrada, intentando reconectar...")
            self._cliente_ssh = None
            
        if not self.host:
            return

        try:
            self._cliente_ssh = paramiko.SSHClient()
            self._cliente_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.user,
                "timeout": 10,
            }
            
            if self.auth_method == "password":
                connect_kwargs["password"] = self.password
                connect_kwargs["look_for_keys"] = False
                connect_kwargs["allow_agent"] = False
            else:
                connect_kwargs["key_filename"] = self.key_path

            self._cliente_ssh.connect(**connect_kwargs)
            self._auto_conectado = True
            logger.info("SSH conectado para monitoreo de sistema a %s:%s (método: %s)", self.host, self.port, self.auth_method)
        except Exception as e:
            logger.error("Error SSH al conectar para sistema: %s", e)
            self._cliente_ssh = None
            raise

    def ejecutar_comando(self, cmd: str) -> str:
        """Ejecuta un comando remoto si hay cliente SSH, o retorna vacío."""
        if self._cliente_ssh is not None:
            transport = self._cliente_ssh.get_transport()
            if transport is None or not transport.is_active():
                logger.warning("Detectado cliente SSH de Sistema desconectado. Forzando reconexión...")
                self._cliente_ssh = None

        if self._cliente_ssh is None:
            self._conectar_ssh()
        if self._cliente_ssh is None:
            return ""
        try:
            # Inyectar el flag -S para que sudo lea la contraseña desde stdin
            if "sudo " in cmd and "sudo -S" not in cmd:
                cmd = cmd.replace("sudo ", "sudo -S ")

            stdin, stdout, stderr = self._cliente_ssh.exec_command(cmd, timeout=10)
            
            # Escribir la contraseña si el comando contiene sudo -S
            if "sudo -S " in cmd and self.password:
                stdin.write(self.password + "\n")
                stdin.flush()

            salida = stdout.read().decode("utf-8", errors="replace").strip()
            return salida
        except Exception as e:
            logger.error("Error ejecutando comando remoto '%s': %s", cmd, e)
            self._cliente_ssh = None
            return ""

    def obtener_cpu(self) -> float:
        """Obtiene el porcentaje de uso de CPU (0 a 100)."""
        if self._externo:
            # Obtener carga de CPU remota
            # Usando /proc/loadavg como aproximación
            salida = self.ejecutar_comando("cat /proc/loadavg")
            if salida:
                partes = salida.split()
                if partes:
                    try:
                        # Obtenemos la carga de 1 min
                        carga_1m = float(partes[0])
                        # Determinar nro de cores para normalizar
                        cores_output = self.ejecutar_comando("nproc")
                        cores = 1
                        if cores_output.strip().isdigit():
                            cores = max(1, int(cores_output.strip()))
                        cpu_porcentaje = min(100.0, (carga_1m / cores) * 100.0)
                        return round(cpu_porcentaje, 1)
                    except (ValueError, IndexError):
                        pass
            # Alternativa usando top
            salida_top = self.ejecutar_comando("top -bn1 | grep 'Cpu(s)'")
            if salida_top:
                # Ejemplo: "%Cpu(s):  5.0 us,  2.0 sy,  0.0 ni, 93.0 id, ..."
                match = re.search(r"(\d+\.\d+)\s+id", salida_top)
                if match:
                    idle = float(match.group(1))
                    return round(100.0 - idle, 1)
            return 0.0
        else:
            return round(psutil.cpu_percent(interval=None) or 0.0, 1)

    def obtener_ram(self) -> dict:
        """Obtiene métricas de RAM: usado (%), total (GB), consumido (GB)."""
        if self._externo:
            # Remoto (free -m)
            salida = self.ejecutar_comando("free -m")
            if salida:
                lineas = salida.splitlines()
                for linea in lineas:
                    if linea.startswith("Mem:"):
                        partes = linea.split()
                        if len(partes) >= 3:
                            try:
                                total_mb = float(partes[1])
                                used_mb = float(partes[2])
                                total_gb = round(total_mb / 1024.0, 1)
                                used_gb = round(used_mb / 1024.0, 1)
                                porcentaje = round((used_mb / total_mb) * 100.0, 1) if total_mb > 0 else 0.0
                                return {
                                    "porcentaje": porcentaje,
                                    "total_gb": total_gb,
                                    "usado_gb": used_gb,
                                }
                            except ValueError:
                                pass
            return {"porcentaje": 0.0, "total_gb": 0.0, "usado_gb": 0.0}
        else:
            # Local (psutil)
            mem = psutil.virtual_memory()
            return {
                "porcentaje": round(mem.percent, 1),
                "total_gb": round(mem.total / (1024.0 ** 3), 1),
                "usado_gb": round(mem.used / (1024.0 ** 3), 1),
            }

    def obtener_disco(self) -> dict:
        """Obtiene métricas de almacenamiento de la partición raíz /: usado (%), total (GB), consumido (GB)."""
        if self._externo:
            # Remoto (df -m /)
            salida = self.ejecutar_comando("df -m /")
            if salida:
                lineas = [l for l in salida.splitlines() if l.strip()]
                for linea in lineas:
                    if not (linea.startswith("Filesystem") or linea.startswith("Sist. Arch") or linea.startswith("Sistemas")):
                        partes = linea.split()
                        if len(partes) >= 4:
                            try:
                                # Formatos comunes de df
                                if len(partes) == 5:
                                    total_mb = float(partes[0])
                                    used_mb = float(partes[1])
                                    pct_str = partes[3].replace("%", "")
                                else:
                                    total_mb = float(partes[1])
                                    used_mb = float(partes[2])
                                    pct_str = partes[4].replace("%", "")
                                total_gb = round(total_mb / 1024.0, 1)
                                used_gb = round(used_mb / 1024.0, 1)
                                porcentaje = float(pct_str)
                                return {
                                    "porcentaje": porcentaje,
                                    "total_gb": total_gb,
                                    "usado_gb": used_gb,
                                }
                            except ValueError:
                                pass
            return {"porcentaje": 0.0, "total_gb": 0.0, "usado_gb": 0.0}
        else:
            # Local (psutil)
            disco = psutil.disk_usage('/')
            return {
                "porcentaje": round(disco.percent, 1),
                "total_gb": round(disco.total / (1024.0 ** 3), 1),
                "usado_gb": round(disco.used / (1024.0 ** 3), 1),
            }

    def obtener_metricas(self) -> dict:
        """Recopila la telemetría completa del sistema."""
        logger.info("Recopilando telemetría del sistema (modo %s)...", "remoto" if self._externo else "local")
        try:
            cpu = self.obtener_cpu()
            ram = self.obtener_ram()
            disco = self.obtener_disco()
            return {
                "origen": "sistema",
                "modo": "remoto" if self._externo else "local",
                "cpu": {
                    "porcentaje": cpu,
                },
                "ram": ram,
                "disco": disco,
                "ok": True,
            }
        except Exception as e:
            logger.error("Error obteniendo métricas del sistema: %s", e)
            return {"origen": "sistema", "ok": False, "error": str(e)}

    def limpiar_logs_vps(self) -> dict:
        """
        Ejecuta limpieza de logs temporales o antiguos en la VPS para liberar espacio.

        Returns:
            dict con: exito (bool), mensaje (str)
        """
        if not self._externo:
            logger.warning("Limpieza de logs local no implementada en profundidad — simulando")
            return {
                "exito": True,
                "mensaje": "Limpieza de archivos temporales locales completada (simulado)",
            }

        logger.warning("Ejecutando limpieza de logs remota en la VPS...")
        
        # Detectar el gestor de paquetes de la distribución remota de forma dinámica
        pkg_clean_cmd = "sudo apt-get clean" # Fallback por defecto (Debian/Ubuntu)
        if self.ejecutar_comando("which pacman"):
            pkg_clean_cmd = "sudo pacman -Sc --noconfirm" # Arch Linux
        elif self.ejecutar_comando("which dnf"):
            pkg_clean_cmd = "sudo dnf clean all"          # Fedora / RHEL nuevo
        elif self.ejecutar_comando("which yum"):
            pkg_clean_cmd = "sudo yum clean all"          # CentOS / RHEL antiguo

        # Comandos en secuencia para limpiar journals, caché de paquetes y archivos de log rotados
        comandos = [
            "sudo journalctl --vacuum-time=3d",
            pkg_clean_cmd,
            "sudo rm -f /var/log/*.gz /var/log/*.[0-9]"
        ]

        resultados = []
        for cmd in comandos:
            salida = self.ejecutar_comando(cmd)
            resultados.append(f"{cmd} -> {salida[:60]}")

        return {
            "exito": True,
            "mensaje": "Logs antiguos y caché de paquetes limpiados correctamente en la VPS",
            "detalles": resultados,
        }

    def desconectar(self) -> None:
        """Cierra la conexión SSH auto-generada."""
        if self._auto_conectado and self._cliente_ssh:
            self._cliente_ssh.close()
            self._cliente_ssh = None
            self._auto_conectado = False
            logger.info("Conexión SSH auto-conectada de sistema cerrada")

    def __del__(self):
        self.desconectar()
