
# looks at every video and determines if frames need to be extracted, if they do then it does it
```
for FP in d66e49ab-52da-40d3-9ba1-96e35b71b14e/*/2023/01/25/**/*.mp4 ; do
    echo $FP | IFS=/ read -r dot camera year month day hour file
    digit=${file:0:1}
    mkdir -p "d66e49ab-52da-40d3-9ba1-96e35b71b14e/frames-${camera}${year}-${month}-${day}_${hour}__${digit}/"
    if [ ! -f "d66e49ab-52da-40d3-9ba1-96e35b71b14e/frames-${camera}${year}-${month}-${day}_${hour}__${digit}/alphapose-results.json" ]
    then
        existing=$(ls d66e49ab-52da-40d3-9ba1-96e35b71b14e/frames-${camera}${year}-${month}-${day}_${hour}__${digit}/ | grep "^${file:0:5}" | wc -l)
        if (( existing < 60 )); then
            echo $FP $existing
            ffmpeg -i $FP "d66e49ab-52da-40d3-9ba1-96e35b71b14e/frames-${camera}${year}-${month}-${day}_${hour}__${digit}/${file:0:5}_%03d.png" > /dev/null 2>&1
        fi
    fi
done
```

# looks at frames blocks and runs alphapose on them if they haven't already been done.
```
for FP in frames-*2023-01-25* ; do
    echo $FP
    if [ ! -f $FP/alphapose-results.json ]
    then
        docker run -v /data:/data  \
            -v /data/dahliasf/d66e49ab-52da-40d3-9ba1-96e35b71b14e:/source \
            --gpus all \
            wildflowerschools/pose-models:alphapose-base-v0 \
            --detector yolox-x \
            --cfg /data/models/halpe_26/config.yaml \
            --checkpoint /data/models/halpe_26/halpe26_fast_res50_256x192.pth \
            --indir /source/$FP \
            --form coco \
            --outdir /source/$FP --gpus 0,1 --sp --detbatch 30 --posebatch 100
        find $FP -name "*.png" -delete
    fi
done
```

# counts the number of files in frame blocks
```
for FP in frames-*2023-01-25_* ; do
    echo "${FP} $(ls $FP | wc -l)"    
done
```

# counts the number of frames that had poses (I think) in results per block
```
for FP in frames-*2023-01-06_19__1 ; do
    if [ -f $FP/alphapose-results.json ]
    then
        echo "${FP} $(/usr/bin/jq '[.[].image_id] | unique | length' $FP/alphapose-results.json)  $(/usr/bin/jq 'length' $FP/alphapose-results.json)"
    fi
done
```

# report of frame blocks, says which are done and which are not with a total at the end
```
let tot=0
let cnt=0
for FP in frames-*2023-01-10* ; do
    tot=$(($tot+1))
    if [ -f $FP/alphapose-results.json ]
    then
        echo "${FP} done"
        cnt=$(($cnt+1))
    else
        echo "${FP} not yet processed"
    fi
done
echo "$cnt or $tot are completed"
```





# find smallish result files, don't recall why
```
find . -name "alphapose-results.json" -type f -size -5b
```


# clears frames that have already been processed, now being done right after alphapose runs.
```
for FP in frames-*2023-01-25* ; do
    if [ -f $FP/alphapose-results.json ]
    then
        find $FP -name "*.png" -delete
    fi
done
```
