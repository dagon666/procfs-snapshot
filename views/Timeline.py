import json
from twisted.web import resource
from twisted.web.template import Element, renderer, XMLFile, flattenString
from twisted.python.filepath import FilePath
from util import LOGGER


class DropdownMenu(Element):
    def __init__(self, template, title, optionsList):
        self.title = title
        self.optionsList = optionsList
        self.loader = XMLFile(FilePath(template))

    @renderer
    def listTitle(self, request, tag):
        return tag(self.title)

    @renderer
    def listItems(self, request, tag):
        for option in self.optionsList:
            yield tag.clone().fillSlots(optionName=option.upper(), pageName='?measure=%s' % option)


class TimelineElement(Element):
    # These are the options used when showing the chart.
    chart_options = {
        'width': 1600,
        'height': 350,
        'enableInteractivity': True,
        # These two options exist according to the Google Chart docs, but they
        # seem to cause the chart to render incorrectly on Chrome.
        # TODO: It would be nice to get the focusTarget option working. That
        #       means you would be selecting a whole vertical slice in the
        #       timeline (ie. a whole snapshot), rather than a single process
        #       in a single snapshot. It's the former that is loaded in the
        #       lower pane after clicking on the timeline.
        # 'explorer': {},
        # 'focusTarget': 'category',
        'chartArea': { 'width': '60%', 'height': '70%' },
        'maxDepth': 1,
        'useWeightedAverageForAggregation': True,
    }
    title_template = '%s Timeline'

    def __init__(self, template, data, measure):
        Element.__init__(self)
        self.loader = XMLFile(FilePath(template))
        self.chart_data = data
        self.chart_options['title'] = self.title_template % measure.upper()

    @renderer
    def options(self, request, tag):
        return json.dumps(self.chart_options)

    @renderer
    def data(self, request, tag):
        return json.dumps(self.chart_data)


class TimelineView(resource.Resource):
    isLeaf = False
    output = ''
    measure_index = {'pss': 4, 'rss': 5, 'uss': 6}

    def __init__(self, db, process_name_filter, measure):
        resource.Resource.__init__(self)
        self.db = db
        self.process_name_filter = process_name_filter
        self.measure = measure.lower()
        self.index = self.measure_index[self.measure]

    def renderOutput(self, output):
        self.output += output

    def getChild(self, name, request):
        LOGGER.info('Rendering child of TimelineView: %s' % name)
        if name == '':
            return self
        return resource.Resource.getChild(self, name, request)

    def render_GET(self, request):
        LOGGER.info('Rendering TimelineView %s' % request.path)

        request.setHeader('content-type', 'text/html')

        processes = []

        # This array will hold all of the data for the timeline view.
        data = [['Timestamp']]

        # Add the list of processes to the timeline table.
        for row in self.db.get_process_cmdlines(name=self.process_name_filter):
            processes.append(row[0])
            data[0].append(row[1].strip())

        LOGGER.debug('got process data: %s' % data)

        # Now add the top-level memory values for the processes to the table.
        for row in self.db.get_process_stats(name=self.process_name_filter):
            timestamp = row[0]
            if timestamp != data[-1][0]:
                # Moved onto a new snapshot
                data.append([0] * (len(processes) + 1))
                data[-1][0] = timestamp

            # Add process for this snapshot
            pos = 1 + processes.index(row[2])
            data[-1][pos] = int(row[self.index])

        flattenString(
            None,
            DropdownMenu('static/dropdown.html',
                         'Memory Measure',
                         self.measure_index.keys())
        ).addCallback(self.renderOutput)
        flattenString(
            None,
            TimelineElement('static/timeline.html', data, self.measure)
        ).addCallback(self.renderOutput)
        request.write(self.output)
        return ""
