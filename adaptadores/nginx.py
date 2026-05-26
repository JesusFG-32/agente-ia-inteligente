"""
adaptadores/nginx.py
====================
Adaptador para monitorear Nginx via SSH usando Paramiko.
Proporciona métricas de estado, conexiones, procesos y logs.
"""

import logging
import re
from typing import Optional

import paramiko

logger = logging.getLogger("agente-ia.nginx")


class AdaptadorNginx:
    """
    Conecta a un servidor remoto via SSH y extrae métricas de Nginx.

    Uso:
        nginx = AdaptadorNginx(host="10.0.0.1", user="ubuntu", key_path="keys/id_rsa")
        metricas = nginx.obtener_metricas()
        nginx.desconectar()
    """

    def __init__(
        self,
        host: str,
        user: str,
        key_path: str = "",
        password: str = "",
        auth_method: str = "key",
        port: int = 22,
        timeout: int = 10,
    ) -> None:
        self.host = host
        self.user = user
        self.key_path = key_path
        self.password = password
        self.auth_method = auth_method.lower() if auth_method else "key"
        self.port = port
        self.timeout = timeout
        self._cliente: Optional[paramiko.SSHClient] = None
        self._conectar()

    # ─── Conexión SSH ─────────────────────────────────────────

    def _conectar(self) -> None:
        """Establece la conexión SSH al servidor remoto."""
        try:
            self._cliente = paramiko.SSHClient()
            self._cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.user,
                "timeout": self.timeout,
            }
            
            if self.auth_method == "password":
                connect_kwargs["password"] = self.password
                connect_kwargs["look_for_keys"] = False
                connect_kwargs["allow_agent"] = False
            else:
                connect_kwargs["key_filename"] = self.key_path

            self._cliente.connect(**connect_kwargs)
            logger.info("SSH conectado a %s:%s (método: %s)", self.host, self.port, self.auth_method)
        except paramiko.AuthenticationException:
            logger.error("Autenticación SSH fallida para %s@%s", self.user, self.host)
            raise
        except paramiko.SSHException as e:
            logger.error("Error SSH al conectar: %s", e)
            raise
        except Exception as e:
            logger.error("Error inesperado en conexión SSH: %s", e)
            raise

    # ─── Ejecución de comandos ────────────────────────────────

    def ejecutar_comando(self, cmd: str) -> dict:
        """
        Ejecuta un comando remoto via SSH.

        Args:
            cmd: Comando shell a ejecutar en el servidor remoto.

        Returns:
            dict con claves: stdout (str), stderr (str), exit_code (int).
        """
        if self._cliente is not None:
            transport = self._cliente.get_transport()
            if transport is None or not transport.is_active():
                logger.warning("Detectado cliente SSH de Nginx desconectado. Forzando reconexión...")
                self._cliente = None

        if self._cliente is None:
            logger.warning("Sin conexión SSH, intentando reconectar...")
            self._conectar()

        try:
            # Inyectar el flag -S para que sudo lea la contraseña desde stdin
            if "sudo " in cmd and "sudo -S" not in cmd:
                cmd = cmd.replace("sudo ", "sudo -S ")

            stdin, stdout, stderr = self._cliente.exec_command(cmd, timeout=self.timeout)
            
            # Escribir la contraseña si el comando contiene sudo -S
            if "sudo -S " in cmd and self.password:
                stdin.write(self.password + "\n")
                stdin.flush()

            salida = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            codigo = stdout.channel.recv_exit_status()
            logger.debug("CMD [%s] exit=%s", cmd, codigo)
            return {"stdout": salida, "stderr": error, "exit_code": codigo}
        except Exception as e:
            logger.error("Error ejecutando comando '%s': %s", cmd, e)
            self._cliente = None
            return {"stdout": "", "stderr": str(e), "exit_code": -1}

    # ─── Métodos de monitoreo ─────────────────────────────────

    def obtener_estado(self) -> dict:
        """
        Verifica el estado del servicio Nginx (activo/inactivo).

        Returns:
            dict con: activo (bool), estado (str), mensaje (str)
        """
        resultado = self.ejecutar_comando("systemctl is-active nginx")
        activo = resultado["stdout"].strip() == "active"
        logger.info("Estado Nginx: %s", resultado["stdout"])
        return {
            "activo": activo,
            "estado": resultado["stdout"].strip() or "desconocido",
            "mensaje": "Nginx operativo" if activo else "Nginx detenido o con error",
        }

    def obtener_conexiones(self) -> dict:
        """
        Cuenta conexiones activas en el puerto 80 y 443.

        Returns:
            dict con: total (int), puerto_80 (int), puerto_443 (int), raw (str)
        """
        resultado = self.ejecutar_comando(
            "ss -tn state established '( dport = :80 or dport = :443 )' | wc -l"
        )
        try:
            total = max(0, int(resultado["stdout"]) - 1)  # resta cabecera
        except ValueError:
            total = 0

        p80 = self.ejecutar_comando(
            "ss -tn state established dport = :80 | wc -l"
        )
        p443 = self.ejecutar_comando(
            "ss -tn state established dport = :443 | wc -l"
        )

        try:
            cnt_80 = max(0, int(p80["stdout"]) - 1)
            cnt_443 = max(0, int(p443["stdout"]) - 1)
        except ValueError:
            cnt_80 = cnt_443 = 0

        logger.info("Conexiones Nginx — total:%s 80:%s 443:%s", total, cnt_80, cnt_443)
        return {
            "total": total,
            "puerto_80": cnt_80,
            "puerto_443": cnt_443,
        }

    def obtener_procesos(self) -> dict:
        """
        Lista procesos Nginx activos en el servidor.

        Returns:
            dict con: cantidad (int), procesos (list[dict])
        """
        resultado = self.ejecutar_comando("ps aux | grep '[n]ginx'")
        lineas = [l for l in resultado["stdout"].splitlines() if l.strip()]
        procesos = []
        for linea in lineas:
            partes = linea.split()
            if len(partes) >= 11:
                procesos.append({
                    "pid": partes[1],
                    "cpu": partes[2],
                    "mem": partes[3],
                    "comando": " ".join(partes[10:]),
                })
        logger.info("Procesos Nginx encontrados: %d", len(procesos))
        return {"cantidad": len(procesos), "procesos": procesos}

    def obtener_logs(self, lineas: int = 50) -> dict:
        """
        Obtiene las últimas líneas del log de acceso de Nginx.

        Args:
            lineas: Número de líneas a retornar (default 50).

        Returns:
            dict con: acceso (list[str]), error (list[str])
        """
        acc = self.ejecutar_comando(f"tail -n {lineas} /var/log/nginx/access.log 2>/dev/null")
        err = self.ejecutar_comando(f"tail -n {lineas} /var/log/nginx/error.log 2>/dev/null")
        return {
            "acceso": acc["stdout"].splitlines(),
            "error": err["stdout"].splitlines(),
        }

    def obtener_metricas(self) -> dict:
        """
        Recopila todas las métricas disponibles de Nginx.

        Returns:
            dict con: estado, conexiones, procesos, logs_error_recientes
        """
        logger.info("Recopilando métricas completas de Nginx...")
        try:
            estado = self.obtener_estado()
            conexiones = self.obtener_conexiones()
            procesos = self.obtener_procesos()
            logs = self.obtener_logs(lineas=20)
            return {
                "origen": "nginx",
                "estado": estado,
                "conexiones": conexiones,
                "procesos": procesos,
                "logs_error_recientes": logs["error"][-10:],
                "ok": True,
            }
        except Exception as e:
            logger.error("Error obteniendo métricas de Nginx: %s", e)
            return {"origen": "nginx", "ok": False, "error": str(e)}

    # ─── Acciones ─────────────────────────────────────────────

    def reiniciar_nginx(self) -> dict:
        """
        Reinicia el servicio Nginx en el servidor remoto.

        Returns:
            dict con: exito (bool), mensaje (str)
        """
        logger.warning("Reiniciando Nginx en %s...", self.host)
        resultado = self.ejecutar_comando("sudo systemctl restart nginx")
        exito = resultado["exit_code"] == 0
        if exito:
            logger.info("Nginx reiniciado exitosamente")
        else:
            logger.error("Error al reiniciar Nginx: %s", resultado["stderr"])
        return {
            "exito": exito,
            "mensaje": "Nginx reiniciado correctamente" if exito else resultado["stderr"],
            "salida": resultado["stdout"],
        }

    # ─── Desconexión ──────────────────────────────────────────

    def desconectar(self) -> None:
        """Cierra la conexión SSH."""
        if self._cliente:
            self._cliente.close()
            self._cliente = None
            logger.info("Conexión SSH con %s cerrada", self.host)

    def __del__(self):
        self.desconectar()
