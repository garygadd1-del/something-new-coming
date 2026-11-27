"""Build a typeperf CSV pair that stands in for a Windows GPU."""

import csv
import io


def _line(fields) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_ALL).writerow(fields)
    return buffer.getvalue().strip()


def pdh(obj: str, counter: str, inst: str = "") -> str:
    if inst:
        return f"\\\\PC\\{obj}({inst})\\{counter}"
    return f"\\\\PC\\{obj}\\{counter}"


def calm_counter_text():
    big = "luid_0x00000000_0x00001234_phys_0"
    small = "luid_0x00000000_0x00000001_phys_0"
    header = [
        "(PDH-CSV 4.0) (UTC)(0)",
        pdh("Memory", "Available MBytes"),
        pdh("Memory", "Committed Bytes"),
        pdh("Memory", "% Committed Bytes In Use"),
        pdh("Memory", "Page Faults/sec"),
        pdh("Memory", "Pages Input/sec"),
        pdh("Memory", "Pages/sec"),
        pdh("Processor Information", "% Processor Utility", "_Total"),
        pdh("Processor Information", "% Processor Utility", "0,0"),
        pdh("Processor Information", "% DPC Time", "_Total"),
        pdh("Processor Information", "% Interrupt Time", "_Total"),
        pdh("Processor Information", "Processor Frequency", "_Total"),
        pdh("Processor Information", "% Processor Performance", "_Total"),
        pdh("Processor Information", "% Performance Limit", "_Total"),
        pdh("System", "Processor Queue Length"),
        pdh("GPU Adapter Memory", "Dedicated Usage", small),
        pdh("GPU Adapter Memory", "Dedicated Usage", big),
        pdh("GPU Engine", "Utilization Percentage", f"pid_4242_{big[:-7]}_phys_0_eng_0_engtype_3d"),
        pdh("GPU Engine", "Utilization Percentage", f"pid_4242_{big[:-7]}_phys_0_eng_1_engtype_compute"),
        pdh("GPU Engine", "Utilization Percentage", f"pid_7_{big[:-7]}_phys_0_eng_2_engtype_3d"),
        pdh("GPU Engine", "Utilization Percentage", f"pid_1_{small[:-7]}_phys_0_eng_0_engtype_3d"),
        pdh("GPU Process Memory", "Dedicated Usage", f"pid_4242_{big}_mem"),
    ]
    # big[:-7] strips "_phys_0" (7 chars) leaving the luid key used inside engine names.
    values = [
        "10/25/2026 12:00:00.000",
        "16384",
        str(8 * 2**30),
        "20",
        "100",
        "10",
        "40",
        "12.5",
        "20",
        "0.1",
        "0.2",
        "4200",
        "100",
        "100",
        "1",
        str(100 * 2**20),
        str(1024 * 2**20),
        "40",
        "10",
        "5",
        "99",
        str(256 * 2**20),
    ]
    return _line(header), _line(values)
