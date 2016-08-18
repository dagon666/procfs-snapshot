import re
from smaps import parse_smaps_memory_region, is_memory_region_header
from meminfo import parse_meminfo
from model import Process, ProcessList, MemoryStats
from util import LOGGER


def _save_smaps_region(output, output2, data):
    data = data.strip()

    if data != '':
        region = parse_smaps_memory_region(data.split('\n'))
        output.append(region)
        output2.append(region)
    else:
        # It's OK if the smaps file is empty.
        #print ('Skipping empty smaps region')
        pass


def _parse_section(section_name, current_process, maps, data):
    if section_name == 'meminfo':
        parse_meminfo(maps, data.split('\n'))
    elif current_process and section_name != '':
        # Hit a new file, consolidate what we have so far.
        if 'smaps' == section_name:
            _save_smaps_region(current_process.maps, maps, data)
        elif 'cmdline' == section_name:
            # Some command lines have a number of empty arguments. Ignore
            # that because it's not interesting here.
            current_process.argv = filter(len, data.strip().split('\0'))


def read_tailed_files(stream):
    section_name = ''
    data = ''
    processes = ProcessList()
    maps = MemoryStats()
    current_process = None

    for line in stream:
        LOGGER.debug('Got line: %s' % line)
        if line == '':
            continue
        # tail gives us lines like:
        #
        #     ==> /proc/99/smaps <==
        #
        # between files
        elif line.startswith('==>'):
            _parse_section(section_name, current_process, maps, data)
            data = ''
            section_name = ''

            # Now parse the new line.
            match = re.match(r'==> /proc/([0-9]+)/([\w]+) <==', line)
            if match is None:
                if '/proc/self/' in line or '/proc/thread-self/' in line:
                    # We just ignore these entries.
                    pass
                elif '/proc/meminfo' in line:
                    section_name = 'meminfo'
                else:
                    # There's probably been an error in the little state machine.
                    LOGGER.error('Error parsing tail line: %s' % line)
            else:
                section_name = match.group(2)
                #print ('Parsing new file: %s' % line)
                current_process = processes.get(pid=int(match.group(1)))

        elif current_process and section_name == 'smaps' and is_memory_region_header(line):
            # We get here on reaching a new memory region in a smaps file.
            _save_smaps_region(current_process.maps, maps, data)
            data = line
        elif section_name != '':
            data += line
        else:
            LOGGER.debug('Skipping line: %s' % line)

    # We've hit the end, parse the section we were in.
    _parse_section(section_name, current_process, maps, data)

    return processes, maps