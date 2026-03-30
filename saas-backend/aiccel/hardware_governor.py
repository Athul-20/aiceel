import psutil
import platform
import logging

logger = logging.getLogger("aiccel.hardware")

class OSGovernor:
    """
    AICCEL Hardware Governor Proof-of-Concept
    =========================================
    Binds empirical AI classification risk scores directly to OS-level 
    Hardware resources (CPU Affinity & System Priority).
    
    This forms the technical basis for the "Hierarchical Resource Gating" patent claim,
    proving that software safety policies can be enforced via physical silicon limits.
    """
    def __init__(self, pid: int = None):
        self.pid = pid or psutil.Process().pid
        try:
            self.process = psutil.Process(self.pid)
            self.os_system = platform.system()
        except psutil.NoSuchProcess:
            self.process = None

    def apply_risk_profile(self, risk_score: float) -> dict:
        """
        Dynamically modulates physical hardware limits based on the AI Risk Score (0.0 - 1.0).
        """
        if not self.process:
            return {"status": "error", "message": "Process not found."}

        try:
            # ---------------------------------------------------------
            # 1. CRITICAL RISK (e.g., Active Prompt Injection detected)
            # Action: Maximum Hardware Jail / Quarantine
            # ---------------------------------------------------------
            if risk_score >= 0.80:
                # Pin to a single "Penalty Core"
                cpu_cores = [0] 
                
                # Drop to lowest OS priority so it cannot starve background services
                if self.os_system == "Windows":
                    priority = getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", getattr(psutil, "IDLE_PRIORITY_CLASS", 32))
                else:
                    priority = 19  # Lowest priority on POSIX
                
                self._apply_cpu_affinity(cpu_cores)
                self._apply_priority(priority)
                
                logger.warning(f"OS-JAIL ACTIVE: Risk Score {risk_score:.2f}. Agent PID {self.pid} quarantined to Core 0.")
                return {"status": "enforced", "level": "critical_jail", "cores": 1, "nice_priority": priority}
                
            # ---------------------------------------------------------
            # 2. ELEVATED RISK (e.g., Suspicious wording, unknown intent)
            # Action: Throttled Hardware Performance
            # ---------------------------------------------------------
            elif risk_score >= 0.50:
                # Restrict to half the physical cores
                cpu_count = max(1, psutil.cpu_count(logical=False) // 2)
                cpu_cores = list(range(cpu_count))
                
                if self.os_system == "Windows":
                    priority = getattr(psutil, "NORMAL_PRIORITY_CLASS", 32)
                else:
                    priority = 0
                
                self._apply_cpu_affinity(cpu_cores)
                self._apply_priority(priority)
                logger.info(f"OS-THROTTLE ACTIVE: Risk Score {risk_score:.2f}. Agent PID {self.pid} limited to {cpu_count} cores.")
                return {"status": "enforced", "level": "elevated_throttle", "cores": cpu_count, "nice_priority": priority}

            # ---------------------------------------------------------
            # 3. SAFE (e.g., Standard trusted operation)
            # Action: Full Hardware Freedom
            # ---------------------------------------------------------
            else:
                # Provide full access to all logical processors
                cpu_cores = list(range(psutil.cpu_count(logical=True)))
                
                if self.os_system == "Windows":
                    priority = getattr(psutil, "HIGH_PRIORITY_CLASS", 32)
                else:
                    priority = -10 # Higher priority on POSIX
                
                self._apply_cpu_affinity(cpu_cores)
                try: 
                     # Only escalate if admin rights allow it
                    self._apply_priority(priority)
                except psutil.AccessDenied:
                    pass 
                
                logger.debug(f"OS-FREE: Risk Score {risk_score:.2f}. Agent PID {self.pid} granted all {len(cpu_cores)} cores.")
                return {"status": "enforced", "level": "safe_free", "cores": len(cpu_cores), "nice_priority": "high/normal"}

        except psutil.AccessDenied:
            logger.error("Hardware Governor lacks OS permissions to enforce limits.")
            return {"status": "failed", "reason": "access_denied"}

    def _apply_cpu_affinity(self, cores: list[int]):
        """Pins the process to specific CPU cores."""
        if hasattr(self.process, "cpu_affinity"):
            self.process.cpu_affinity(cores)
            
    def _apply_priority(self, priority_level: int):
        """Sets the OS CPU scheduling priority."""
        self.process.nice(priority_level)
