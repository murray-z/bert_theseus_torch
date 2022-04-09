# _*_ coding:utf-8 _*_
import torch
from torch.utils.data import DataLoader
from transformers.optimization import AdamW
from bert_model import *
from utils import *
from config import *
from data_helper import TheseusDataSet
from seqeval.metrics import accuracy_score
from seqeval.metrics import f1_score
from seqeval.metrics import classification_report


label2idx = load_json(label2idx_path)
idx2label = {i: l for l, i in label2idx.items()}
PAD_IDX = label2idx["<PAD>"]

train_dataloader = DataLoader(TheseusDataSet(train_data_path), batch_size=batch_size, shuffle=True)
dev_dataloader = DataLoader(TheseusDataSet(dev_data_path), batch_size=batch_size, shuffle=False)
test_dataloader = DataLoader(TheseusDataSet(test_data_path), batch_size=batch_size, shuffle=False)


def calculate(true_labels, pred_labels):
    true_labels = [true_labels]
    pred_labels = [pred_labels]
    f1 = f1_score(true_labels, pred_labels)
    acc = accuracy_score(true_labels, pred_labels)
    report = classification_report(true_labels, pred_labels)
    return f1, acc, report


def dev(model, data_loader, criterion):
    model.eval()
    all_pred_tags = []
    all_true_tags = []
    all_loss = []
    with torch.no_grad():
        for i, batch in enumerate(data_loader):
            batch = [d.to(device) for d in batch]
            true_tags = batch[-1]
            pred_tags = model(*batch[:3])
            flatten_pred_tags = pred_tags.view(-1, pred_tags.size()[2])
            flatten_true_tags = true_tags.view(-1)
            loss = criterion(flatten_pred_tags, flatten_true_tags)
            all_loss.append(loss.item())

            flatten_pred_tags = flatten_pred_tags.cpu()
            flatten_true_tags = flatten_true_tags.cpu()
            flatten_pred_tags = torch.argmax(flatten_pred_tags, dim=1)

            flatten_pred_tags = [idx2label[id.item()] for id in flatten_pred_tags]
            flatten_true_tags = [idx2label[id.item()] for id in flatten_true_tags]

            all_pred_tags.extend(flatten_pred_tags)
            all_true_tags.extend(flatten_true_tags)

    loss = sum(all_loss) / len(all_loss)
    f1, acc, report = calculate(all_true_tags, all_pred_tags)

    return f1, acc, report, loss


def train(model, model_save_path):
    # 开始训练
    print("Training ......")
    print(model)
    # 优化器
    optimizer = AdamW(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, 1, gamma=0.95)
    criterion = nn.CrossEntropyLoss(ignore_index=PAD_IDX)

    # 开始训练
    best_f1 = 0.
    for epoch in range(1, epochs+1):
        model.train()
        for i, batch in enumerate(train_dataloader):
            optimizer.zero_grad()
            batch = [d.to(device) for d in batch]
            true_tags = batch[-1]
            pred_tags = model(*batch[:3])
            flatten_pred_tags = pred_tags.view(-1, pred_tags.size()[2])
            flatten_true_tags = true_tags.view(-1)
            loss = criterion(flatten_pred_tags, flatten_true_tags)
            loss.backward()
            optimizer.step()

            if i % 100 == 0:
                flatten_pred_tags = flatten_pred_tags.cpu()
                flatten_true_tags = flatten_true_tags.cpu()
                flatten_pred_tags = torch.argmax(flatten_pred_tags, dim=1)

                # 类别id转成汉字
                flatten_pred_tags = [idx2label[id.item()] for id in flatten_pred_tags]
                flatten_true_tags = [idx2label[id.item()] for id in flatten_true_tags]

                f1, acc, report = calculate(flatten_true_tags, flatten_pred_tags)

                print("TRAIN STEP:{} F1:{} ACC:{} LOSS:{}".format(i, f1, acc, loss.item()))

        # 验证
        f1, acc, report, loss = dev(model, dev_dataloader, criterion)
        if f1 > best_f1:
            best_f1 = f1
            torch.save(model.state_dict(), model_save_path)
        print("DEV EPOCH:{} F1:{} ACC:{} LOSS:{}".format(epoch, f1, acc, loss))
        print("REPORT:\n{}".format(report))

    # 测试
    model = model.load_state_dict(torch.load(model_save_path))
    f1, acc, report, loss = dev(model, test_dataloader, criterion)
    print("TEST F1:{} ACC:{} LOSS:{}".format(f1, acc, loss))
    print("REPORT:\n{}".format(report))


if __name__ == '__main__':
    predecessor_model = Predecessor(config_path=predecessor_config_path,
                                    pretrained_model_path=predecessor_model_path,
                                    classification_layer=classification_layer)

    successor_model = Successor(config_path=successor_config_path,
                                classification_layer=classification_layer)

    # fine-tuning predecessor model
    train(predecessor_model, model_save_path=best_predecessor_model_path)

    # train theseus
    # 加载最优predecessor model
    predecessor_model.load_state_dict(torch.load(best_predecessor_model_path))
    theseus_model = Theseus(predecessor_model, successor_model,
                            classification_layer=classification_layer)
    train(theseus_model, model_save_path=best_theseus_model_path)

    # fine-tuning successor model
    # 加载最优theseus model
    theseus_model.load_state_dict(torch.load(best_theseus_model_path))
    train(theseus_model.successor, model_save_path=best_successor_model_path)





