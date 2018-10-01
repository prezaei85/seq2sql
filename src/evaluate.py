from __future__ import division
from builtins import bytes
import os
import argparse
import math
import codecs
import torch

from table.Translator import Translator
import table.IO
import opts
from itertools import takewhile, count
try:
    from itertools import zip_longest
except ImportError:
    from itertools import izip_longest as zip_longest
from path import Path
import glob
import json
from tqdm import tqdm
from lib.dbengine import DBEngine
from lib.query import Query

import pdb

parser = argparse.ArgumentParser(description='evaluate.py')
opts.translate_opts(parser)
opt = parser.parse_args()
torch.cuda.set_device(opt.gpu)
opt.anno = os.path.join(
    opt.anno_data_path, '{}.jsonl'.format(opt.split))
opt.source_file = os.path.join(
    opt.data_path, '{}.jsonl'.format(opt.split))
opt.db_file = os.path.join(opt.data_path, '{}.db'.format(opt.split))
opt.pre_word_vecs = os.path.join(opt.data_path, 'embedding')
print('Evaluating model on the {} set.'.format(opt.split))

def main():
    dummy_parser = argparse.ArgumentParser(description='train.py')
    opts.model_opts(dummy_parser)
    opts.train_opts(dummy_parser)
    dummy_opt = dummy_parser.parse_known_args([])[0]

    engine = DBEngine(opt.db_file)

    with codecs.open(opt.source_file, "r", "utf-8") as corpus_file:
        sql_list = [json.loads(line)['sql'] for line in corpus_file]

    js_list = table.IO.read_anno_json(opt.anno)

    prev_best = (None, None)
    for fn_model in glob.glob(opt.model_path):

        opt.model = fn_model

        translator = Translator(opt, dummy_opt.__dict__)
        data = table.IO.TableDataset(js_list, translator.fields, None, False)
        test_data = table.IO.OrderedIterator(
            dataset=data, device=opt.gpu, batch_size=opt.batch_size, train=False, sort=True, sort_within_batch=False)

        # inference
        if opt.beam_search:
            print('Using beam search for inference.')
        r_list = []
        for batch in test_data:
            r_list += translator.translate(batch, js_list, sql_list)
        r_list.sort(key=lambda x: x.idx)

        #pdb.set_trace()

        assert len(r_list) == len(js_list), 'len(r_list) != len(js_list): {} != {}'.format(
            len(r_list), len(js_list))

        # evaluation
        for pred, gold, sql_gold in zip(r_list, js_list, sql_list):

            #pdb.set_trace()

            pred.eval(gold, sql_gold, engine)
        print('Results:')
        for metric_name in ('all', 'exe'):
            c_correct = sum((x.correct[metric_name] for x in r_list))
            print('{}: {} / {} = {:.2%}'.format(metric_name, c_correct,
                                                len(r_list), c_correct / len(r_list)))
            if metric_name == 'all' and (prev_best[0] is None or c_correct > prev_best[1]):
                prev_best = (fn_model, c_correct)

    if (opt.split == 'dev') and (prev_best[0] is not None):
        with codecs.open(os.path.join(opt.data_path, 'dev_best.txt'), 'w', encoding='utf-8') as f_out:
            f_out.write('{}\n'.format(prev_best[0]))


if __name__ == "__main__":
    main()