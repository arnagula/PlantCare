"""Illustrative ML pipeline trained on *synthetic threshold-derived labels*, not plant ground truth."""
from pathlib import Path
import random
from aws.model import ISSUES

def main():
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.metrics import classification_report
    rng=random.Random(42)
    def make(n):
        out=[]
        for i in range(n):
            temp=rng.uniform(12,36); rh=rng.uniform(20,85); lux=rng.uniform(0,6000); soil=rng.uniform(0,100)
            xs=[temp,rh,lux,soil]
            ys=[int(soil>80),int(soil<30),int(temp>27),int(temp<16),int(rh<50),int(lux<1100)]
            out.append((xs,ys))
        return out
    train=make(800);test=make(200)
    model=DecisionTreeClassifier(max_depth=7,random_state=42)
    model.fit([x for x,y in train],[y for x,y in train])
    ypred=model.predict([x for x,y in test]); ytest=[y for x,y in test]
    print(classification_report(ytest,ypred,target_names=ISSUES,zero_division=0))
    print('CAUTION: synthetic rule labels are not a real-world accuracy evaluation.')
    import joblib
    dst=Path(__file__).with_name('synthetic_example_model.joblib');joblib.dump(model,dst);print('Saved',dst)
if __name__=='__main__': main()
