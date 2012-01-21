import sys, csv
from sys import stderr, stdout

import networkx as nx
import matplotlib.pyplot as plot
from utils import pslparser


MIN_INTRON = 21
MIN_UTR = 100

exonDb = {}
intronDb = {}
clusters = {}

class ExonObj:
    def __init__(self, chrom, start, end):
        self.chrom = chrom
        self.start = start
        self.end = end
        self.terminal = None
        self.nextExons = set([])
        self.introns = set([])

    def __str__(self):
        return '%s:%d-%d' % (self.chrom, self.start, self.end)


def parsePSL(filename):
    '''Reads alignments from PSL format and create
    exon objects from each transcript.

    '''

    for pslObj in pslparser.read(open(filename)):
        exons = []
        for i in range(len(pslObj.attrib['tStarts'])):
            exonStart = pslObj.attrib['tStarts'][i]
            exonEnd = exonStart + pslObj.attrib['blockSizes'][i]

            exon = ExonObj(pslObj.attrib['tName'], exonStart, exonEnd)
            exons.append(exon)

        yield exons


def addIntrons(exons, intronDb, exonDb, clusters, clusterNo):
    '''Get introns from a set of exons.'''

    existingClusters = set([])

    introns = []

    for i in range(len(exons)):
        currExon = exonDb[str(exons[i])]
        try:
            nextExon = exonDb[str(exons[i + 1])]
        except IndexError:
            pass
        else:
            currExon.nextExons.add(str(nextExon))

            intronStart = currExon.end + 1
            intronEnd = nextExon.start - 1

            intronName = '%s:%d-%d' % (currExon.chrom, intronStart, intronEnd)
            intron = nx.DiGraph(name=intronName, cluster=None)

            try:
                intron_ = intronDb[intron.graph['name']]
            except KeyError:

                intronDb[intron.graph['name']] = intron
                intron.add_edge(str(currExon), str(nextExon))
                introns.append(intron)
                currExon.introns.add(intron.graph['name'])
                nextExon.introns.add(intron.graph['name'])
            else:
                intron_.add_edge(str(currExon), str(nextExon))
                introns.append(intron_)
                existingClusters.add(intron_.graph['cluster'])
                currExon.introns.add(intron_.graph['name'])
                nextExon.introns.add(intron_.graph['name'])

    assert len(introns) == len(exons) - 1

    if not existingClusters:
        cluster = nx.DiGraph()
        if len(introns) > 1:
            cluster.add_path([i.graph['name'] for i in introns])
            for intron in introns:
                intron.graph['cluster'] = clusterNo
        else:
            cluster.add_node(introns[0].graph['name'])
            introns[0].graph['cluster'] = clusterNo

    else:
        cluster = nx.DiGraph(exons=set([]))
        for cl in existingClusters:
            cluster.add_edges_from(clusters[cl].edges())
            k = clusters.pop(cl)

        for intron in cluster.nodes():
            intronDb[intron].graph['cluster'] = clusterNo

        if len(introns) > 1:
            cluster.add_path([i.graph['name'] for i in introns])

            for intron in introns:
                intron.graph['cluster'] = clusterNo
        else:
            cluster.add_node(introns[0].graph['name'])
            introns[0].graph['cluster'] = clusterNo

    clusters[clusterNo] = cluster

    return clusterNo


def collapseExons(g, exonDb):
    # g = an exon graph.

    exons = [exonDb[e] for e in g.nodes()]
    sortedExons = sorted(exons, key=lambda x: (x.end, x.start))

    i = 0
    currExon = sortedExons[i]
    while i <= len(sortedExons):
        try:
            nextExon = sortedExons[i + 1]
        except IndexError:
            pass
        else:
            if currExon.end == nextExon.end:
                if nextExon.terminal == 1:
                    g.add_edges_from([(str(currExon), n)\
                            for n in g.successors(str(nextExon))])
                    g.remove_node(str(nextExon))
                else:
                    if currExon.terminal == 1:
                        if nextExon.start - currExon.start <= MIN_UTR:
                            g.add_edges_from([(str(nextExon), n)\
                                    for n in g.successors(str(currExon))])
                            g.remove_node(str(currExon))

                    currExon = nextExon
            else:
                currExon = nextExon
        i += 1

    i = 0
    exons = [exonDb[e] for e in g.nodes()]
    sortedExons = sorted(exons, key=lambda x: (x.start, x.end))
    currExon = sortedExons[0]
    while i <= len(sortedExons):
        try:
            nextExon = sortedExons[i + 1]
        except IndexError:
            pass
        else:
            if currExon.start == nextExon.start:
                if currExon.terminal == 2:
                    g.add_edges_from([(n, str(nextExon))\
                            for n in g.predecessors(str(currExon))])
                    g.remove_node(str(currExon))
                    currExon = nextExon
                else:
                    if nextExon.terminal == 2:
                        if nextExon.end - currExon.end <= MIN_UTR:
                            g.add_edges_from([(n, str(currExon))\
                                    for n in g.predecessors(str(nextExon))])
                            g.remove_node(str(nextExon))
                        else:
                            currExon = nextExon
                    else:
                        currExon = nextExon
            else:
                currExon = nextExon
        i += 1


def deleteGap(exons):
    i = 0

    newExon = []
    currExon = exons[i]

    while True:
        try:
            nextExon = exons[i + 1]
        except IndexError:
            break
        else:
            if nextExon.start - currExon.end <= MIN_INTRON:
                currExon.end = nextExon.end
            else:
                newExon.append(currExon)
                currExon = nextExon
        i += 1

    newExon.append(currExon)
    return newExon


def addExon(db, exons):
    '''1.Change a terminal attribute of a leftmost exon
    and a rightmost exon to 1 and 2 respectively.
    A terminal attribute has a value 'None' by default.

    2.Add exons to the exon database (db).

    '''
    exons[0].terminal = 1
    exons[-1].terminal = 2

    for exon in exons:
        try:
            exon_ = db[str(exon)]
        except KeyError:
            db[str(exon)] = exon
        else:
            if not exon.terminal and exon_.terminal:
                exon_.terminal = None


def mergeClusters(exonDb):
    bigCluster = nx.Graph()
    for exon in exonDb.itervalues():
        path = []
        for intron in exon.introns:
            path.append(intronDb[intron].graph['cluster'])

        if len(path) > 1:
            bigCluster.add_path(path)
        elif len(path) == 1:
            bigCluster.add_node(path[0])
        else:
            raise ValueError, 'Cannot merge empty path'

    return bigCluster


def walkDown(intronCoord, path, allPath, cluster):
    '''Returns all downstream exons from a given exon.'''

    if cluster.successors(intronCoord) == []:
        allPath.append(path[:])
        return
    else:
        for nex in cluster.successors(intronCoord):
            if nex not in path:
                path.append(nex)

            walkDown(nex, path, allPath, cluster)

            path.pop()


def getPath(cluster):
    '''Returns all paths of a given cluster.'''

    roots = [node for node in cluster.nodes() \
                    if not cluster.predecessors(node)]
    allPaths = []

    for root in roots:
        path = [root]
        walkDown(root, path, allPaths, cluster)

    return allPaths


def buildSpliceGraph(cluster, intronDb, exonDb, mergedExons):
    allPaths = getPath(cluster)

    g = nx.DiGraph()
    for path in allPaths:
        for intronCoord in path:
            intron = intronDb[intronCoord]
            for exon in intron.exons:
                for nextExon in exonDb[exon].nextExons:
                    if nextExon not in mergedExons:
                        g.add_edge(exon, nextExon)

    return g


def printBedGraph(transcript, geneId, tranId):
    '''Print a splice graph in BED format.'''

    exons = sorted([exonDb[e] for e in transcript],
                            key=lambda x: (x.start, x.end))

    chromStart = exons[0].start
    chromEnd = exons[-1].end
    chrom = exons[0].chrom

    blockStarts = ','.join([str(exon.start - chromStart) for exon in exons])
    blockSizes = ','.join([str(exon.end - exon.start) for exon in exons])

    name = '%s:%d.%d' % (chrom, geneId, tranId)
    score = 1000
    itemRgb = '0,0,0'
    thickStart = chromStart
    thickEnd = chromEnd
    strand = '+'
    blockCount = len(exons)

    writer = csv.writer(stdout, dialect='excel-tab')
    writer.writerow((chrom,
                    chromStart,
                    chromEnd,
                    name,
                    score,
                    strand,
                    thickStart,
                    thickEnd,
                    itemRgb,
                    blockCount,
                    blockSizes,
                    blockStarts))


def buildGeneModels(exonDb, intronDb, clusters, bigCluster):
    print >> stderr, 'Building gene models...'

    removedClusters = set([])
    numTranscripts = 0
    geneId = 0

    for cl_num, cl in enumerate(bigCluster.nodes(), start=1):
        if cl not in removedClusters:
            g = nx.DiGraph()
            for intron in clusters[cl].nodes():
                g.add_edges_from(intronDb[intron].edges())

            for neighbor in bigCluster.neighbors(cl):
                if neighbor != cl: # chances are node connects to itself.
                    neighborCluster = clusters[neighbor]
                    for intron in neighborCluster.nodes():
                        g.add_edges_from(intronDb[intron].edges())

                removedClusters.add(neighbor)
            removedClusters.add(cl)

            if g.nodes():
                geneId += 1
                transId = 1
                collapseExons(g, exonDb)

                for transcript in getPath(g):
                    printBedGraph(transcript, geneId, transId)
                    numTranscripts += 1
                    transId += 1
        if cl_num % 1000 == 0:
            print >> sys.stderr, '...', cl_num

    return geneId, numTranscripts


def main(inputFile):
    clusterNo = 0

    print >> stderr, 'Parsing alignments from %s...' % inputFile
    for n, exons in enumerate(parsePSL(inputFile), start=1):

        '''Alignments may contain small gaps.
        The program fills up the gaps for simplicity's sake. 
        A minimum size of a gap can be adjusted by assigning a new
        value to MIN_INTRON in line 8.

        '''

        exons = deleteGap(exons)  # delete intron <= MIN_INTRON

        if len(exons) > 1:
            ''' The program ignores all single exons.'''
            addExon(exonDb, exons)
            addIntrons(exons, intronDb, exonDb, clusters, clusterNo)
            clusterNo += 1
        else:
            exons[0].single = True

        if n % 1000 == 0:
            print >> stderr, '...', n

    bigCluster = mergeClusters(exonDb)
    geneId, numTranscripts = buildGeneModels(exonDb,
                                    intronDb, clusters, bigCluster)

    print >> stderr, '\nTotal exons = %d' % len(exonDb)
    print >> stderr, 'Total genes = %d' % geneId
    print >> stderr, 'Total transcripts = %d' % (numTranscripts)
    print >> stderr, 'Isoform/gene = %.2f' % (float(numTranscripts) / len(clusters))


if __name__=='__main__':
    inputFile = sys.argv[1]
    main(inputFile)